from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select

from app.api.deps import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    require,
    resolve_branch_id,
)
from app.core.exceptions import PermissionDeniedError
from app.core.permissions import Permission
from app.models.catalog import Product
from app.models.inventory import StockItem, StockMovement
from app.models.tenant import Branch
from app.schemas.common import Page
from app.schemas.inventory import (
    StockAdjustIn,
    StockCountIn,
    StockLevelOut,
    StockMovementOut,
)
from app.services import inventory_service

router = APIRouter(prefix="/inventory", tags=["inventory"])


@router.get(
    "/levels",
    response_model=Page[StockLevelOut],
    dependencies=[Depends(require(Permission.STOCK_READ))],
)
async def stock_levels(
    db: DbSession,
    user: CurrentUser,
    branch_id: uuid.UUID | None = None,
    search: str | None = Query(default=None, max_length=100),
    low_only: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> Page[StockLevelOut]:
    effective_branch = resolve_branch_id(user, branch_id)

    threshold = func.coalesce(StockItem.low_stock_threshold, Product.low_stock_threshold)
    conditions = [Product.deleted_at.is_(None), Product.track_stock.is_(True)]
    if effective_branch:
        conditions.append(StockItem.branch_id == effective_branch)
    if search:
        term = f"%{search.lower()}%"
        conditions.append(
            or_(func.lower(Product.name).like(term), func.lower(Product.sku).like(term))
        )
    if low_only:
        conditions.append(threshold > 0)
        conditions.append(StockItem.quantity <= threshold)

    total = await db.scalar(
        select(func.count())
        .select_from(StockItem)
        .join(Product, Product.id == StockItem.product_id)
        .where(*conditions)
    )

    rows = (
        await db.execute(
            select(
                Product.id,
                Product.name,
                Product.sku,
                Product.barcode,
                Product.unit,
                Product.cost_price,
                Branch.id,
                Branch.name,
                StockItem.quantity,
                StockItem.reserved_quantity,
                threshold,
            )
            .select_from(StockItem)
            .join(Product, Product.id == StockItem.product_id)
            .join(Branch, Branch.id == StockItem.branch_id)
            .where(*conditions)
            .order_by(StockItem.quantity, Product.name)
            .offset((page - 1) * size)
            .limit(size)
        )
    ).all()

    items = []
    for row in rows:
        quantity = Decimal(row[8])
        reserved = Decimal(row[9])
        limit = Decimal(row[10])
        items.append(
            StockLevelOut(
                product_id=row[0],
                product_name=row[1],
                sku=row[2],
                barcode=row[3],
                unit=row[4].value,
                cost_price=Decimal(row[5]),
                branch_id=row[6],
                branch_name=row[7],
                quantity=quantity,
                reserved_quantity=reserved,
                available=quantity - reserved,
                low_stock_threshold=limit,
                is_low=limit > 0 and quantity <= limit,
                stock_value=(quantity * Decimal(row[5])).quantize(Decimal("0.01")),
            )
        )

    return Page[StockLevelOut](items=items, total=total or 0, page=page, size=size)


@router.post(
    "/adjust",
    response_model=StockMovementOut,
    dependencies=[Depends(require(Permission.STOCK_ADJUST))],
)
async def adjust_stock(
    payload: StockAdjustIn, db: DbSession, user: CurrentUser, tenant: CurrentTenant
) -> StockMovement:
    """Apply a signed delta: deliveries, waste, corrections."""
    branch_id = resolve_branch_id(user, payload.branch_id)
    if branch_id is None:
        raise PermissionDeniedError("No branch selected.")

    return await inventory_service.adjust_stock(
        db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        product_id=payload.product_id,
        delta=payload.quantity,
        movement_type=payload.movement_type,
        user_id=user.id,
        unit_cost=payload.unit_cost,
        supplier_id=payload.supplier_id,
        note=payload.note,
    )


@router.post(
    "/count",
    response_model=StockMovementOut,
    dependencies=[Depends(require(Permission.STOCK_ADJUST))],
)
async def record_count(
    payload: StockCountIn, db: DbSession, user: CurrentUser, tenant: CurrentTenant
) -> StockMovement:
    """A stocktake. Records the difference, which is the shrinkage figure."""
    branch_id = resolve_branch_id(user, payload.branch_id)
    if branch_id is None:
        raise PermissionDeniedError("No branch selected.")

    return await inventory_service.record_count(
        db,
        tenant_id=tenant.id,
        branch_id=branch_id,
        product_id=payload.product_id,
        counted=payload.counted_quantity,
        user_id=user.id,
        note=payload.note,
    )


@router.get(
    "/movements",
    response_model=Page[StockMovementOut],
    dependencies=[Depends(require(Permission.STOCK_READ))],
)
async def list_movements(
    db: DbSession,
    user: CurrentUser,
    product_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
) -> Page[StockMovementOut]:
    """The append-only ledger. This is what makes on-hand reconstructable."""
    conditions = []
    if product_id:
        conditions.append(StockMovement.product_id == product_id)
    effective_branch = resolve_branch_id(user, branch_id)
    if effective_branch:
        conditions.append(StockMovement.branch_id == effective_branch)

    total = await db.scalar(select(func.count()).select_from(StockMovement).where(*conditions))
    rows = await db.scalars(
        select(StockMovement)
        .where(*conditions)
        .order_by(StockMovement.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    return Page[StockMovementOut](
        items=[StockMovementOut.model_validate(row) for row in rows],
        total=total or 0,
        page=page,
        size=size,
    )
