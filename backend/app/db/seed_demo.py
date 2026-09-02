"""Demo catalog for a tenant, so the POS has something to sell.

Run with:  python -m app.db.seed_demo <shop-slug>
"""

from __future__ import annotations

import asyncio
import logging
import sys
from decimal import Decimal

from sqlalchemy import select

from app.db.session import AsyncSessionLocal, session_tenant_scope
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.catalog import Category, Product, ProductBarcode, TaxRate
from app.models.enums import ProductUnit, StockMovementType
from app.models.inventory import StockItem, StockMovement
from app.models.tenant import Branch, Tenant

logger = logging.getLogger(__name__)

CATEGORIES = [
    ("Drinks", "#0ea5e9"),
    ("Bakery", "#f59e0b"),
    ("Produce", "#22c55e"),
    ("Snacks", "#ec4899"),
    ("Household", "#8b5cf6"),
]

# (category, name, sku, barcode, price, cost, unit, stock)
PRODUCTS = [
    (
        "Drinks",
        "Cola 330ml can",
        "DRK-001",
        "5449000000996",
        "1.20",
        "0.65",
        ProductUnit.PIECE,
        240,
    ),
    (
        "Drinks",
        "Sparkling water 1L",
        "DRK-002",
        "5060335635013",
        "0.95",
        "0.42",
        ProductUnit.PIECE,
        120,
    ),
    (
        "Drinks",
        "Orange juice 1L",
        "DRK-003",
        "8410179000015",
        "2.40",
        "1.30",
        ProductUnit.PIECE,
        48,
    ),
    (
        "Drinks",
        "Cold brew coffee",
        "DRK-004",
        "7622210449283",
        "2.85",
        "1.55",
        ProductUnit.PIECE,
        36,
    ),
    ("Bakery", "Sourdough loaf", "BAK-001", "2000000000015", "3.50", "1.40", ProductUnit.PIECE, 18),
    ("Bakery", "Croissant", "BAK-002", "2000000000022", "1.60", "0.55", ProductUnit.PIECE, 24),
    ("Bakery", "Cinnamon bun", "BAK-003", "2000000000039", "2.10", "0.80", ProductUnit.PIECE, 12),
    ("Produce", "Bananas", "PRD-001", "2100000000012", "1.90", "0.95", ProductUnit.KG, 30),
    ("Produce", "Tomatoes", "PRD-002", "2100000000029", "3.20", "1.70", ProductUnit.KG, 22),
    (
        "Produce",
        "Baby spinach 200g",
        "PRD-003",
        "2100000000036",
        "2.25",
        "1.10",
        ProductUnit.PIECE,
        16,
    ),
    (
        "Snacks",
        "Salted crisps 150g",
        "SNK-001",
        "5000328000114",
        "1.75",
        "0.80",
        ProductUnit.PIECE,
        60,
    ),
    (
        "Snacks",
        "Dark chocolate 100g",
        "SNK-002",
        "7622300336738",
        "2.40",
        "1.15",
        ProductUnit.PIECE,
        44,
    ),
    (
        "Snacks",
        "Mixed nuts 250g",
        "SNK-003",
        "8712345678905",
        "4.60",
        "2.40",
        ProductUnit.PIECE,
        20,
    ),
    (
        "Household",
        "Kitchen roll 2pk",
        "HSE-001",
        "5010026500019",
        "2.80",
        "1.35",
        ProductUnit.PACK,
        30,
    ),
    (
        "Household",
        "Dish soap 500ml",
        "HSE-002",
        "5011417551103",
        "1.95",
        "0.90",
        ProductUnit.PIECE,
        25,
    ),
    (
        "Household",
        "Bin bags 20pk",
        "HSE-003",
        "5000204512052",
        "3.40",
        "1.60",
        ProductUnit.PACK,
        14,
    ),
]

# Carton barcodes: one scan adds a whole case.
PACK_BARCODES = [
    ("DRK-001", "15449000000993", 24, "24-can case"),
    ("SNK-001", "15000328000111", 12, "12-bag case"),
]


async def seed_demo(slug: str) -> None:
    async with AsyncSessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant)
            .where(Tenant.slug == slug)
            .execution_options(**{SKIP_TENANT_FILTER: True})
        )
        if tenant is None:
            raise SystemExit(f"No shop with slug {slug!r}")

        async with session_tenant_scope(session, tenant.id):
            branch = await session.scalar(
                select(Branch)
                .where(Branch.tenant_id == tenant.id)
                .order_by(Branch.is_default.desc())
            )
            if branch is None:
                raise SystemExit("Shop has no branch")

            if await session.scalar(select(Product.id).limit(1)):
                logger.info("Catalog already seeded; nothing to do")
                return

            vat = TaxRate(
                tenant_id=tenant.id,
                name="VAT 20%",
                rate=Decimal("0.20"),
                is_inclusive=True,  # European shelf prices include VAT
                is_default=True,
            )
            zero = TaxRate(
                tenant_id=tenant.id,
                name="Zero rated",
                rate=Decimal("0"),
                is_inclusive=True,
            )
            session.add_all([vat, zero])
            await session.flush()

            categories: dict[str, Category] = {}
            for index, (name, color) in enumerate(CATEGORIES):
                category = Category(
                    tenant_id=tenant.id,
                    name=name,
                    slug=name.lower(),
                    color=color,
                    sort_order=index,
                )
                session.add(category)
                categories[name] = category
            await session.flush()

            products: dict[str, Product] = {}
            for cat, name, sku, barcode, price, cost, unit, _stock in PRODUCTS:
                # Food is zero-rated in many places; this gives the cart a mix
                # of rates to exercise.
                tax = zero if cat in {"Bakery", "Produce"} else vat
                product = Product(
                    tenant_id=tenant.id,
                    category_id=categories[cat].id,
                    tax_rate_id=tax.id,
                    name=name,
                    sku=sku,
                    barcode=barcode,
                    unit=unit,
                    price=Decimal(price),
                    cost_price=Decimal(cost),
                    track_stock=True,
                    low_stock_threshold=Decimal("10"),
                    is_favorite=sku in {"DRK-001", "BAK-002", "SNK-001", "PRD-001"},
                )
                session.add(product)
                products[sku] = product
            await session.flush()

            for sku, code, pack_size, label in PACK_BARCODES:
                session.add(
                    ProductBarcode(
                        tenant_id=tenant.id,
                        product_id=products[sku].id,
                        code=code,
                        pack_size=Decimal(pack_size),
                        label=label,
                    )
                )

            for _, _, sku, _, _, _, _, stock in PRODUCTS:
                product = products[sku]
                session.add(
                    StockItem(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        product_id=product.id,
                        quantity=Decimal(stock),
                    )
                )
                session.add(
                    StockMovement(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        product_id=product.id,
                        movement_type=StockMovementType.INITIAL,
                        quantity=Decimal(stock),
                        quantity_after=Decimal(stock),
                        unit_cost=product.cost_price,
                        note="Demo seed",
                    )
                )

            await session.commit()

    logger.info("Seeded %d products for %s", len(PRODUCTS), slug)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(seed_demo(sys.argv[1] if len(sys.argv) > 1 else "corner"))
