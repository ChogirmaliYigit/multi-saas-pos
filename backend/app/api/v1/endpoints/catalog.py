from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from slugify import slugify
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import selectinload

from app.api.deps import (
    CurrentTenant,
    CurrentUser,
    DbSession,
    require,
    resolve_branch_id,
)
from app.core import quotas
from app.core.exceptions import ConflictError, NotFoundError
from app.core.permissions import Permission, permissions_for
from app.models.catalog import Category, Product, ProductBarcode, TaxRate
from app.models.enums import StockMovementType
from app.models.inventory import StockItem
from app.schemas.catalog import (
    CategoryIn,
    CategoryOut,
    CategoryUpdate,
    ProductDetail,
    ProductIn,
    ProductListItem,
    ProductLookupOut,
    ProductOut,
    ProductUpdate,
    TaxRateIn,
    TaxRateOut,
)
from app.schemas.common import Message, Page
from app.services import inventory_service

router = APIRouter(prefix="/catalog", tags=["catalog"])


def _to_out(product: Product, stock: Decimal | None) -> ProductOut:
    threshold = product.low_stock_threshold or Decimal("0")
    return ProductOut(
        id=product.id,
        name=product.name,
        sku=product.sku,
        barcode=product.barcode,
        category_id=product.category_id,
        unit=product.unit,
        price=product.price,
        image_url=product.image_url,
        track_stock=product.track_stock,
        is_favorite=product.is_favorite,
        tax_rate=product.tax_rate.rate if product.tax_rate else Decimal("0"),
        tax_inclusive=product.tax_rate.is_inclusive if product.tax_rate else False,
        stock_quantity=stock,
        low_stock=(
            product.track_stock and stock is not None and threshold > 0 and stock <= threshold
        ),
    )


@router.get("/categories", response_model=list[CategoryOut])
async def list_categories(
    db: DbSession,
    _: Annotated[object, Depends(require(Permission.CATEGORY_READ))],
) -> list[Category]:
    result = await db.scalars(
        select(Category)
        .where(Category.is_active.is_(True), Category.deleted_at.is_(None))
        .order_by(Category.sort_order, Category.name)
    )
    return list(result)


@router.get("/products", response_model=Page[ProductListItem])
async def list_products(
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.PRODUCT_READ))],
    search: str | None = Query(default=None, max_length=100),
    category_id: uuid.UUID | None = None,
    branch_id: uuid.UUID | None = None,
    favorites_only: bool = False,
    page: int = Query(1, ge=1),
    size: int = Query(60, ge=1, le=200),
) -> Page[ProductListItem]:
    """The POS grid.

    Stock is LEFT JOINed for the terminal's branch, so a product with no stock
    row still appears (as zero) rather than vanishing from the grid.
    """
    effective_branch = resolve_branch_id(user, branch_id)

    conditions = [Product.is_active.is_(True), Product.deleted_at.is_(None)]
    if category_id:
        conditions.append(Product.category_id == category_id)
    if favorites_only:
        conditions.append(Product.is_favorite.is_(True))
    if search:
        term = f"%{search.lower()}%"
        conditions.append(
            or_(
                func.lower(Product.name).like(term),
                func.lower(Product.sku).like(term),
                Product.barcode == search,
            )
        )

    total = await db.scalar(select(func.count()).select_from(Product).where(*conditions))

    stmt = (
        select(Product, StockItem.quantity)
        .outerjoin(
            StockItem,
            (StockItem.product_id == Product.id) & (StockItem.branch_id == effective_branch),
        )
        .options(selectinload(Product.tax_rate), selectinload(Product.category))
        .where(*conditions)
        .order_by(Product.is_favorite.desc(), Product.name)
        .offset((page - 1) * size)
        .limit(size)
    )

    rows = (await db.execute(stmt)).all()

    # Cost and margin are owner/manager data. A cashier browsing the POS grid
    # has no business seeing what the shop pays, so the fields are left out at
    # the source rather than hidden by the UI.
    may_see_cost = Permission.PRODUCT_COST_READ in permissions_for(
        user.role, user.permission_overrides
    )

    items = [
        ProductListItem(
            **_to_out(product, stock if product.track_stock else None).model_dump(),
            cost_price=product.cost_price if may_see_cost else None,
            category_name=product.category.name if product.category else None,
            low_stock_threshold=product.low_stock_threshold,
            is_active=product.is_active,
        )
        for product, stock in rows
    ]

    return Page[ProductListItem](items=items, total=total or 0, page=page, size=size)


@router.get("/lookup", response_model=ProductLookupOut)
async def lookup_by_code(
    db: DbSession,
    user: CurrentUser,
    _: Annotated[object, Depends(require(Permission.PRODUCT_READ))],
    code: str = Query(min_length=1, max_length=64),
    branch_id: uuid.UUID | None = None,
) -> ProductLookupOut:
    """Resolve a scanned code. The hottest path in the whole product.

    Order of attempts is deliberate: primary barcode first (the overwhelming
    majority of scans), then pack barcodes, then SKU as a manual-entry
    fallback. Each is a single indexed lookup.
    """
    effective_branch = resolve_branch_id(user, branch_id)
    code = code.strip()

    async def stock_for(product: Product) -> Decimal | None:
        if not product.track_stock:
            return None
        return await db.scalar(
            select(StockItem.quantity).where(
                StockItem.product_id == product.id,
                StockItem.branch_id == effective_branch,
            )
        )

    base = (
        select(Product)
        .options(selectinload(Product.tax_rate))
        .where(Product.deleted_at.is_(None), Product.is_active.is_(True))
    )

    product = await db.scalar(base.where(Product.barcode == code))
    if product is not None:
        return ProductLookupOut(
            product=_to_out(product, await stock_for(product)),
            pack_size=Decimal("1"),
            matched_on="barcode",
        )

    pack = await db.scalar(
        select(ProductBarcode)
        .options(selectinload(ProductBarcode.product).selectinload(Product.tax_rate))
        .where(ProductBarcode.code == code)
    )
    if pack is not None and pack.product is not None:
        return ProductLookupOut(
            product=_to_out(pack.product, await stock_for(pack.product)),
            pack_size=pack.pack_size,
            matched_on="pack_barcode",
        )

    product = await db.scalar(base.where(func.lower(Product.sku) == code.lower()))
    if product is not None:
        return ProductLookupOut(
            product=_to_out(product, await stock_for(product)),
            pack_size=Decimal("1"),
            matched_on="sku",
        )

    raise NotFoundError(
        f"No product matches “{code}”.",
        code="product_not_found",
        details={"code": code},
    )


# ---------------------------------------------------------------------------
# Admin writes. Reads above are open to cashiers; everything below needs the
# manage permission, which cashiers do not hold.
# ---------------------------------------------------------------------------


@router.post(
    "/categories",
    response_model=CategoryOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.CATEGORY_MANAGE))],
)
async def create_category(payload: CategoryIn, db: DbSession) -> Category:
    slug = slugify(payload.name)[:140]
    if await db.scalar(select(Category.id).where(Category.slug == slug)):
        raise ConflictError("A category with that name already exists.", code="slug_taken")

    category = Category(**payload.model_dump(), slug=slug)
    db.add(category)
    await db.flush()
    return category


@router.patch(
    "/categories/{category_id}",
    response_model=CategoryOut,
    dependencies=[Depends(require(Permission.CATEGORY_MANAGE))],
)
async def update_category(
    category_id: uuid.UUID, payload: CategoryUpdate, db: DbSession
) -> Category:
    category = await db.scalar(
        select(Category).where(Category.id == category_id, Category.deleted_at.is_(None))
    )
    if category is None:
        raise NotFoundError("Category not found.")

    updates = payload.model_dump(exclude_unset=True)
    if "parent_id" in updates and updates["parent_id"] == category_id:
        raise ConflictError("A category cannot be its own parent.", code="cyclic_parent")
    for field, value in updates.items():
        setattr(category, field, value)
    if "name" in updates:
        category.slug = slugify(category.name)[:140]

    await db.flush()
    return category


@router.delete(
    "/categories/{category_id}",
    response_model=Message,
    dependencies=[Depends(require(Permission.CATEGORY_MANAGE))],
)
async def delete_category(category_id: uuid.UUID, db: DbSession) -> Message:
    category = await db.scalar(
        select(Category).where(Category.id == category_id, Category.deleted_at.is_(None))
    )
    if category is None:
        raise NotFoundError("Category not found.")

    # Soft delete. Historical orders reference products which reference this
    # category; a hard delete would either cascade into sales history or fail.
    category.deleted_at = func.now()
    category.is_active = False
    await db.execute(
        update(Product).where(Product.category_id == category_id).values(category_id=None)
    )
    return Message(message="Category removed.")


@router.post(
    "/products",
    response_model=ProductDetail,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def create_product(
    payload: ProductIn, db: DbSession, user: CurrentUser, tenant: CurrentTenant
) -> ProductDetail:
    await quotas.assert_can_add_product(db, tenant.id)

    if await db.scalar(select(Product.id).where(Product.sku == payload.sku)):
        raise ConflictError(f"SKU {payload.sku} is already in use.", code="sku_taken")
    if payload.barcode and await db.scalar(
        select(Product.id).where(Product.barcode == payload.barcode, Product.deleted_at.is_(None))
    ):
        raise ConflictError(f"Barcode {payload.barcode} is already in use.", code="barcode_taken")

    data = payload.model_dump(exclude={"opening_stock"})
    product = Product(**data)
    db.add(product)
    await db.flush()

    # Opening stock goes through the ledger like any other movement, so the
    # very first quantity is auditable rather than appearing from nowhere.
    if payload.opening_stock and payload.opening_stock > 0:
        branch_id = resolve_branch_id(user, None)
        if branch_id:
            await inventory_service.adjust_stock(
                db,
                tenant_id=tenant.id,
                branch_id=branch_id,
                product_id=product.id,
                delta=payload.opening_stock,
                movement_type=StockMovementType.INITIAL,
                user_id=user.id,
                note="Opening stock",
            )

    await db.refresh(product, ["tax_rate", "category"])
    return _to_detail(product, payload.opening_stock)


@router.get(
    "/products/{product_id}",
    response_model=ProductDetail,
    dependencies=[Depends(require(Permission.PRODUCT_READ))],
)
async def get_product(product_id: uuid.UUID, db: DbSession, user: CurrentUser) -> ProductDetail:
    product = await db.scalar(
        select(Product)
        .options(selectinload(Product.tax_rate), selectinload(Product.category))
        .where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        raise NotFoundError("Product not found.")

    branch_id = resolve_branch_id(user, None)
    stock = None
    if product.track_stock and branch_id:
        stock = await db.scalar(
            select(StockItem.quantity).where(
                StockItem.product_id == product.id, StockItem.branch_id == branch_id
            )
        )
    return _to_detail(product, stock)


@router.patch(
    "/products/{product_id}",
    response_model=ProductDetail,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def update_product(
    product_id: uuid.UUID, payload: ProductUpdate, db: DbSession
) -> ProductDetail:
    product = await db.scalar(
        select(Product)
        .options(selectinload(Product.tax_rate), selectinload(Product.category))
        .where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        raise NotFoundError("Product not found.")

    updates = payload.model_dump(exclude_unset=True)

    if (
        "sku" in updates
        and updates["sku"] != product.sku
        and await db.scalar(
            select(Product.id).where(Product.sku == updates["sku"], Product.id != product_id)
        )
    ):
        raise ConflictError(f"SKU {updates['sku']} is already in use.", code="sku_taken")

    if (
        updates.get("barcode")
        and updates["barcode"] != product.barcode
        and await db.scalar(
            select(Product.id).where(
                Product.barcode == updates["barcode"],
                Product.id != product_id,
                Product.deleted_at.is_(None),
            )
        )
    ):
        raise ConflictError(
            f"Barcode {updates['barcode']} is already in use.", code="barcode_taken"
        )

    for field, value in updates.items():
        setattr(product, field, value)
    await db.flush()
    await db.refresh(product, ["tax_rate", "category"])
    return _to_detail(product, None)


@router.delete(
    "/products/{product_id}",
    response_model=Message,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def delete_product(product_id: uuid.UUID, db: DbSession) -> Message:
    product = await db.scalar(
        select(Product).where(Product.id == product_id, Product.deleted_at.is_(None))
    )
    if product is None:
        raise NotFoundError("Product not found.")

    # Soft delete: order_items point here, and a receipt reprinted next year
    # must still resolve. Deactivating also pulls it from the POS grid.
    product.deleted_at = func.now()
    product.is_active = False
    return Message(message="Product removed.")


@router.get(
    "/tax-rates",
    response_model=list[TaxRateOut],
    dependencies=[Depends(require(Permission.PRODUCT_READ))],
)
async def list_tax_rates(db: DbSession) -> list[TaxRate]:
    result = await db.scalars(
        select(TaxRate).where(TaxRate.deleted_at.is_(None)).order_by(TaxRate.name)
    )
    return list(result)


@router.post(
    "/tax-rates",
    response_model=TaxRateOut,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(require(Permission.PRODUCT_MANAGE))],
)
async def create_tax_rate(payload: TaxRateIn, db: DbSession) -> TaxRate:
    if await db.scalar(select(TaxRate.id).where(TaxRate.name == payload.name)):
        raise ConflictError("A tax rate with that name already exists.", code="name_taken")

    if payload.is_default:
        # Only one default, or product creation becomes non-deterministic.
        await db.execute(update(TaxRate).values(is_default=False))

    rate = TaxRate(**payload.model_dump())
    db.add(rate)
    await db.flush()
    return rate


def _to_detail(product: Product, stock: Decimal | None) -> ProductDetail:
    base = _to_out(product, stock if product.track_stock else None)
    return ProductDetail(
        **base.model_dump(),
        description=product.description,
        cost_price=product.cost_price,
        category_name=product.category.name if product.category else None,
        tax_rate_id=product.tax_rate_id,
        tax_rate_name=product.tax_rate.name if product.tax_rate else None,
        low_stock_threshold=product.low_stock_threshold,
        is_active=product.is_active,
    )
