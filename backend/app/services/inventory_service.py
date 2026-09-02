"""Stock movements.

Every change to on-hand quantity goes through here so the `stock_movements`
ledger stays complete. Reconstructing stock from the ledger is what makes
shrinkage visible; a direct UPDATE somewhere else silently breaks that.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError
from app.models.catalog import Product
from app.models.enums import StockMovementType
from app.models.inventory import StockItem, StockMovement
from app.services.pricing import quantity as q


async def _ensure_stock_row(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
) -> StockItem:
    """Get or create the (branch, product) stock row.

    Upsert rather than select-then-insert: two adjustments racing on a product
    that has never been stocked would otherwise both try to INSERT and one
    would hit the unique constraint.
    """
    await session.execute(
        text(
            """
            INSERT INTO stock_items
                (id, tenant_id, branch_id, product_id, quantity,
                 reserved_quantity, created_at, updated_at)
            VALUES (gen_random_uuid(), :tenant_id, :branch_id, :product_id, 0,
                    0, now(), now())
            ON CONFLICT (tenant_id, branch_id, product_id) DO NOTHING
            """
        ),
        {"tenant_id": tenant_id, "branch_id": branch_id, "product_id": product_id},
    )
    item = await session.scalar(
        select(StockItem).where(
            StockItem.branch_id == branch_id, StockItem.product_id == product_id
        )
    )
    if item is None:  # pragma: no cover - the upsert above guarantees a row
        raise NotFoundError("Stock row could not be created.")
    return item


async def adjust_stock(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    delta: Decimal,
    movement_type: StockMovementType,
    user_id: uuid.UUID | None = None,
    unit_cost: Decimal | None = None,
    supplier_id: uuid.UUID | None = None,
    note: str | None = None,
    reference_type: str | None = None,
    reference_id: uuid.UUID | None = None,
) -> StockMovement:
    """Apply a signed delta and record it.

    Manual adjustments are allowed to go negative: a correction downward on a
    product whose count was already wrong is exactly the case an operator needs
    to be able to enter. Sales are the path that refuses to oversell.
    """
    product = await session.scalar(
        select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        raise NotFoundError("Product not found.", code="product_not_found")

    await _ensure_stock_row(
        session, tenant_id=tenant_id, branch_id=branch_id, product_id=product_id
    )

    row = (
        await session.execute(
            text(
                """
                UPDATE stock_items
                   SET quantity = quantity + :delta, updated_at = now()
                 WHERE tenant_id = :tenant_id
                   AND branch_id = :branch_id
                   AND product_id = :product_id
             RETURNING quantity
                """
            ),
            {
                "delta": q(delta),
                "tenant_id": tenant_id,
                "branch_id": branch_id,
                "product_id": product_id,
            },
        )
    ).first()

    movement = StockMovement(
        tenant_id=tenant_id,
        branch_id=branch_id,
        product_id=product_id,
        created_by_id=user_id,
        supplier_id=supplier_id,
        movement_type=movement_type,
        quantity=q(delta),
        quantity_after=Decimal(row[0]),
        unit_cost=unit_cost if unit_cost is not None else product.cost_price,
        reference_type=reference_type,
        reference_id=reference_id,
        note=note,
    )
    session.add(movement)
    await session.flush()
    return movement


async def record_count(
    session: AsyncSession,
    *,
    tenant_id: uuid.UUID,
    branch_id: uuid.UUID,
    product_id: uuid.UUID,
    counted: Decimal,
    user_id: uuid.UUID | None = None,
    note: str | None = None,
) -> StockMovement:
    """A physical stocktake.

    The operator enters what is actually on the shelf; the ledger records the
    *difference*, because that difference is the shrinkage figure a manager
    needs. Storing the absolute count alone would hide it.
    """
    item = await _ensure_stock_row(
        session, tenant_id=tenant_id, branch_id=branch_id, product_id=product_id
    )
    delta = q(counted) - item.quantity

    movement = await adjust_stock(
        session,
        tenant_id=tenant_id,
        branch_id=branch_id,
        product_id=product_id,
        delta=delta,
        movement_type=StockMovementType.ADJUSTMENT,
        user_id=user_id,
        note=note or f"Stock count: {item.quantity} -> {q(counted)}",
    )
    item.last_counted_at = movement.created_at
    return movement
