"""A demo shop with a trading history, for showing the product to someone.

`seed_demo` gives a tenant a catalog so the till has something to sell. This
goes further: staff, customers, suppliers, and eight weeks of sales, so the
dashboard, the analytics charts and the reports all have something real to
draw. A demo where every chart reads zero demonstrates nothing.

Run with:  python -m app.db.seed_showcase <shop-slug>

The tenant must already exist -- create it through /auth/signup so the plan,
subscription, owner and default branch come from the real code path rather
than from assumptions made here.

Deterministic: the same slug seeded twice produces the same history, so a
screenshot taken today still matches the data next week.
"""

from __future__ import annotations

import asyncio
import logging
import random
import sys
import uuid as uuid_lib
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy import delete, select

from app.core.security import hash_password, hash_pin
from app.db.session import AsyncSessionLocal, session_tenant_scope
from app.db.tenant_filter import SKIP_TENANT_FILTER
from app.models.catalog import Category, Product, ProductBarcode, Supplier, TaxRate
from app.models.enums import (
    DiscountType,
    OrderStatus,
    PaymentMethod,
    PaymentStatus,
    ProductUnit,
    ShiftStatus,
    StockMovementType,
    UserRole,
)
from app.models.inventory import StockItem, StockMovement
from app.models.sales import Customer, Order, OrderItem, Payment, Refund, Shift
from app.models.tenant import Branch, Tenant
from app.models.user import User
from app.services import pricing

logger = logging.getLogger(__name__)

WEEKS_OF_HISTORY = 8
DEMO_PASSWORD = "Demo2026!parol"
SEED = 20260906  # fixed, so the demo is reproducible

# --------------------------------------------------------------------------
# Catalog -- an Uzbek mini-market, priced in so'm
# --------------------------------------------------------------------------

CATEGORIES = [
    ("Ichimliklar", "#0284c7"),
    ("Non va shirinliklar", "#b45309"),
    ("Sut mahsulotlari", "#0f766e"),
    ("Meva-sabzavot", "#15803d"),
    ("Bakaleya", "#a16207"),
    ("Maishiy tovarlar", "#7c3aed"),
]

# Basic food is zero-rated here so the receipts show a mix of rates rather
# than one number repeated down the page.
ZERO_RATED = {"Non va shirinliklar", "Meva-sabzavot"}

# (category, name, sku, barcode, price, cost, unit, opening stock, popularity)
# Popularity is a relative weight for how often the item lands in a basket.
PRODUCTS = [
    (
        "Ichimliklar",
        "Coca-Cola 0.5L",
        "ICH-001",
        "5449000054227",
        8000,
        5200,
        ProductUnit.PIECE,
        240,
        10,
    ),
    (
        "Ichimliklar",
        "Ichimlik suvi 1.5L",
        "ICH-002",
        "4780007770012",
        4000,
        2400,
        ProductUnit.PIECE,
        300,
        12,
    ),
    (
        "Ichimliklar",
        "Choy 'Ahmad' 100g",
        "ICH-003",
        "0054881003018",
        22000,
        15000,
        ProductUnit.PIECE,
        60,
        4,
    ),
    (
        "Ichimliklar",
        "Sharbat 'Yashnabod' 1L",
        "ICH-004",
        "4780014120037",
        18000,
        12000,
        ProductUnit.PIECE,
        80,
        5,
    ),
    (
        "Ichimliklar",
        "Energetik 'Flash' 0.45L",
        "ICH-005",
        "4780016560048",
        12000,
        8000,
        ProductUnit.PIECE,
        90,
        3,
    ),
    (
        "Non va shirinliklar",
        "Oddiy non",
        "NON-001",
        "2300000000011",
        4000,
        2200,
        ProductUnit.PIECE,
        150,
        14,
    ),
    (
        "Non va shirinliklar",
        "Patir non",
        "NON-002",
        "2300000000028",
        7000,
        4000,
        ProductUnit.PIECE,
        80,
        7,
    ),
    (
        "Non va shirinliklar",
        "Somsa (go'shtli)",
        "NON-003",
        "2300000000035",
        8000,
        4500,
        ProductUnit.PIECE,
        90,
        8,
    ),
    (
        "Non va shirinliklar",
        "Tort 'Praga' 1kg",
        "NON-004",
        "2300000000042",
        95000,
        60000,
        ProductUnit.PIECE,
        8,
        1,
    ),
    (
        "Non va shirinliklar",
        "Pechenye 'Yubileynoe'",
        "NON-005",
        "4600699500018",
        9500,
        6000,
        ProductUnit.PACK,
        70,
        4,
    ),
    (
        "Sut mahsulotlari",
        "Sut 1L",
        "SUT-001",
        "4780004520014",
        12000,
        8500,
        ProductUnit.PIECE,
        120,
        11,
    ),
    (
        "Sut mahsulotlari",
        "Qatiq 0.5L",
        "SUT-002",
        "4780004520021",
        9000,
        6000,
        ProductUnit.PIECE,
        80,
        6,
    ),
    (
        "Sut mahsulotlari",
        "Tvorog 250g",
        "SUT-003",
        "4780004520038",
        16000,
        11000,
        ProductUnit.PIECE,
        45,
        3,
    ),
    (
        "Sut mahsulotlari",
        "Sariyog' 200g",
        "SUT-004",
        "4780004520045",
        28000,
        20000,
        ProductUnit.PIECE,
        40,
        3,
    ),
    (
        "Sut mahsulotlari",
        "Pishloq 'Rossiyskiy'",
        "SUT-005",
        "4780004520052",
        85000,
        62000,
        ProductUnit.KG,
        20,
        2,
    ),
    ("Meva-sabzavot", "Kartoshka", "MEV-001", "2400000000014", 6000, 3800, ProductUnit.KG, 250, 9),
    ("Meva-sabzavot", "Piyoz", "MEV-002", "2400000000021", 4500, 2800, ProductUnit.KG, 180, 7),
    ("Meva-sabzavot", "Pomidor", "MEV-003", "2400000000038", 14000, 9000, ProductUnit.KG, 100, 8),
    ("Meva-sabzavot", "Bodring", "MEV-004", "2400000000045", 12000, 7500, ProductUnit.KG, 90, 6),
    ("Meva-sabzavot", "Olma", "MEV-005", "2400000000052", 16000, 11000, ProductUnit.KG, 110, 6),
    ("Meva-sabzavot", "Banan", "MEV-006", "2400000000069", 22000, 16000, ProductUnit.KG, 70, 5),
    (
        "Bakaleya",
        "Guruch 'Lazer' 1kg",
        "BAK-001",
        "4780012340016",
        18000,
        13000,
        ProductUnit.KG,
        160,
        6,
    ),
    ("Bakaleya", "Un 1kg", "BAK-002", "4780012340023", 7500, 5000, ProductUnit.KG, 220, 7),
    ("Bakaleya", "Shakar 1kg", "BAK-003", "4780012340030", 12000, 8500, ProductUnit.KG, 190, 7),
    (
        "Bakaleya",
        "Yog' 'Oleyna' 1L",
        "BAK-004",
        "4820022080011",
        26000,
        19000,
        ProductUnit.PIECE,
        95,
        5,
    ),
    ("Bakaleya", "Makaron 400g", "BAK-005", "4780012340047", 8000, 5200, ProductUnit.PACK, 130, 5),
    ("Bakaleya", "Tuz 1kg", "BAK-006", "4780012340054", 3000, 1800, ProductUnit.PACK, 110, 4),
    (
        "Maishiy tovarlar",
        "Sovun 'Safeguard'",
        "MAI-001",
        "4902430698184",
        11000,
        7500,
        ProductUnit.PIECE,
        65,
        3,
    ),
    (
        "Maishiy tovarlar",
        "Kir yuvish kukuni 3kg",
        "MAI-002",
        "4780018890015",
        68000,
        50000,
        ProductUnit.PACK,
        25,
        2,
    ),
    (
        "Maishiy tovarlar",
        "Idish yuvish vositasi",
        "MAI-003",
        "4780018890022",
        15000,
        10000,
        ProductUnit.PIECE,
        50,
        3,
    ),
    (
        "Maishiy tovarlar",
        "Salfetka 100 dona",
        "MAI-004",
        "4780018890039",
        9000,
        6000,
        ProductUnit.PACK,
        60,
        3,
    ),
    (
        "Maishiy tovarlar",
        "Tish pastasi",
        "MAI-005",
        "8714789673158",
        18000,
        12500,
        ProductUnit.PIECE,
        45,
        3,
    ),
]

FAVORITES = {"ICH-001", "ICH-002", "NON-001", "NON-003", "SUT-001", "MEV-001"}

# One scan adds a whole case.
PACK_BARCODES = [
    ("ICH-001", "15449000054224", 24, "24 tali yashik"),
    ("ICH-002", "14780007770019", 6, "6 tali paket"),
]

# (full name, email local part, role, pin)
STAFF = [
    ("Nigora Yusupova", "nigora", UserRole.MANAGER, "2468"),
    ("Aziz Tursunov", "aziz", UserRole.CASHIER, "1234"),
    ("Malika Sobirova", "malika", UserRole.CASHIER, "5678"),
]

CUSTOMERS = [
    ("Sardor Aliyev", "+998 90 123 45 67"),
    ("Kamola Rashidova", "+998 91 234 56 78"),
    ("Jasur Ergashev", "+998 93 345 67 89"),
    ("Feruza Qodirova", "+998 94 456 78 90"),
    ("Bekzod Nazarov", "+998 97 567 89 01"),
    ("Zilola Umarova", "+998 99 678 90 12"),
]

SUPPLIERS = [
    ("Toshkent Oziq-Ovqat MChJ", "Rustam Sharipov", "+998 71 200 30 40"),
    ("Farg'ona Sut Kombinati", "Oybek Yo'ldoshev", "+998 73 244 55 66"),
    ("Chilonzor Ulgurji Bazasi", "Shahnoza Ismoilova", "+998 71 277 88 99"),
]

# Roughly how a corner shop's day goes: a morning bread run, a lunch peak,
# and the heaviest hour on the way home from work.
HOUR_WEIGHTS = {
    8: 5,
    9: 7,
    10: 6,
    11: 7,
    12: 11,
    13: 12,
    14: 8,
    15: 7,
    16: 9,
    17: 13,
    18: 15,
    19: 12,
    20: 8,
    21: 4,
}

PAYMENT_MIX = [
    (PaymentMethod.CASH, 42),
    (PaymentMethod.CARD, 46),
    (PaymentMethod.MOBILE, 10),
    (PaymentMethod.BANK_TRANSFER, 2),
]


def _money(value) -> Decimal:
    return pricing.money(Decimal(value))


async def _reset(session, tenant: Tenant) -> None:
    """Clear a demo shop's trading data so it can be seeded again.

    Seeded history is anchored to the day it was generated, so "today" on a
    demo dashboard goes empty after a day. Re-running with --reset is how you
    move it forward, rather than hand-deleting rows.

    Only ever point this at a demo shop: it removes real orders if the shop
    has any.
    """
    owner_id = await session.scalar(
        select(User.id).where(User.role == UserRole.OWNER).order_by(User.created_at)
    )
    default_branch_id = await session.scalar(
        select(Branch.id).order_by(Branch.is_default.desc(), Branch.created_at)
    )

    # Order matters only where the database does not cascade for us.
    for model in (
        Refund,
        Payment,
        OrderItem,
        Order,
        Shift,
        StockMovement,
        StockItem,
        ProductBarcode,
        Product,
        Category,
        TaxRate,
        Customer,
        Supplier,
    ):
        await session.execute(delete(model))

    await session.execute(delete(User).where(User.id != owner_id))
    await session.execute(delete(Branch).where(Branch.id != default_branch_id))
    await session.flush()


async def seed_showcase(slug: str, *, reset: bool = False) -> dict:
    rng = random.Random(SEED)

    async with AsyncSessionLocal() as session:
        tenant = await session.scalar(
            select(Tenant)
            .where(Tenant.slug == slug)
            .execution_options(**{SKIP_TENANT_FILTER: True})
        )
        if tenant is None:
            raise SystemExit(f"No shop with slug {slug!r}. Create it via /auth/signup first.")

        async with session_tenant_scope(session, tenant.id):
            if reset:
                await _reset(session, tenant)

            if await session.scalar(select(Order.id).limit(1)):
                logger.info("Shop already has sales; nothing to do")
                return {"skipped": True}

            owner = await session.scalar(
                select(User).where(User.role == UserRole.OWNER).order_by(User.created_at)
            )
            if owner is None:
                raise SystemExit("Shop has no owner")

            branch = await session.scalar(
                select(Branch).order_by(Branch.is_default.desc(), Branch.created_at)
            )
            if branch is None:
                raise SystemExit("Shop has no branch")

            # ------------------------------------------------------------------
            # Shop identity
            # ------------------------------------------------------------------
            tenant.name = "Demo Market"
            tenant.legal_name = '"Demo Market" MChJ'
            tenant.tax_number = "301234567"
            tenant.phone = "+998 71 200 10 20"
            tenant.address = "Toshkent sh., Chilonzor t., Bunyodkor ko'chasi 12"
            tenant.receipt_header = "Demo Market\nChilonzor filiali"
            tenant.receipt_footer = "Xaridingiz uchun rahmat!\nQaytarish 14 kun ichida, chek bilan."
            tenant.settings = {**(tenant.settings or {}), "receipt_width_mm": 80}

            branch.name = "Chilonzor"
            branch.code = "CHL"
            branch.address = "Bunyodkor ko'chasi 12"
            branch.phone = "+998 71 200 10 20"

            second = Branch(
                tenant_id=tenant.id,
                name="Yunusobod",
                code="YUN",
                address="Amir Temur shoh ko'chasi 108",
                phone="+998 71 200 10 21",
                is_default=False,
                is_active=True,
            )
            session.add(second)

            # ------------------------------------------------------------------
            # Tax rates, categories, products
            # ------------------------------------------------------------------
            qqs = TaxRate(
                tenant_id=tenant.id,
                name="QQS 12%",
                rate=Decimal("0.12"),
                is_inclusive=True,  # shelf prices in Uzbekistan include VAT
                is_default=True,
            )
            zero = TaxRate(
                tenant_id=tenant.id, name="QQS yo'q (0%)", rate=Decimal("0"), is_inclusive=True
            )
            session.add_all([qqs, zero])
            await session.flush()

            categories: dict[str, Category] = {}
            for index, (name, color) in enumerate(CATEGORIES):
                category = Category(
                    tenant_id=tenant.id,
                    name=name,
                    slug=f"cat-{index + 1}",
                    color=color,
                    sort_order=index,
                )
                session.add(category)
                categories[name] = category

            for name, contact, phone in SUPPLIERS:
                session.add(
                    Supplier(tenant_id=tenant.id, name=name, contact_name=contact, phone=phone)
                )
            await session.flush()

            products: dict[str, Product] = {}
            for cat, name, sku, barcode, price, cost, unit, _stock, _pop in PRODUCTS:
                product = Product(
                    tenant_id=tenant.id,
                    category_id=categories[cat].id,
                    tax_rate_id=(zero if cat in ZERO_RATED else qqs).id,
                    name=name,
                    sku=sku,
                    barcode=barcode,
                    unit=unit,
                    price=Decimal(price),
                    cost_price=Decimal(cost),
                    track_stock=True,
                    low_stock_threshold=Decimal("15"),
                    is_favorite=sku in FAVORITES,
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

            # ------------------------------------------------------------------
            # Staff
            # ------------------------------------------------------------------
            owner.full_name = "Dilshod Rahimov"
            owner.phone = "+998 90 100 10 10"
            owner.pin_hash = hash_pin("9999")
            owner.branch_id = branch.id

            staff: list[User] = []
            for full_name, local, role, pin in STAFF:
                member = User(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    email=f"{local}@demo.joinpay.uz",
                    full_name=full_name,
                    phone=None,
                    hashed_password=hash_password(DEMO_PASSWORD),
                    pin_hash=hash_pin(pin),
                    role=role,
                    is_active=True,
                )
                session.add(member)
                staff.append(member)
            await session.flush()

            cashiers = [m for m in staff if m.role is UserRole.CASHIER]
            manager = next(m for m in staff if m.role is UserRole.MANAGER)

            customers: list[Customer] = []
            for name, phone in CUSTOMERS:
                customer = Customer(tenant_id=tenant.id, name=name, phone=phone)
                session.add(customer)
                customers.append(customer)
            await session.flush()

            # ------------------------------------------------------------------
            # Opening stock
            # ------------------------------------------------------------------
            stock: dict[str, Decimal] = {}
            stock_items: dict[str, StockItem] = {}
            for _cat, _name, sku, _bc, _p, _c, _u, opening, _pop in PRODUCTS:
                quantity = Decimal(opening)
                stock[sku] = quantity
                item = StockItem(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    product_id=products[sku].id,
                    quantity=quantity,
                )
                session.add(item)
                stock_items[sku] = item

            history_start = datetime.now(UTC) - timedelta(weeks=WEEKS_OF_HISTORY)
            opened_at = history_start - timedelta(days=1)
            for _cat, _name, sku, _bc, _p, _c, _u, opening, _pop in PRODUCTS:
                session.add(
                    StockMovement(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        product_id=products[sku].id,
                        movement_type=StockMovementType.INITIAL,
                        quantity=Decimal(opening),
                        quantity_after=Decimal(opening),
                        unit_cost=products[sku].cost_price,
                        note="Boshlang'ich qoldiq",
                        created_at=opened_at,
                        updated_at=opened_at,
                    )
                )

            # ------------------------------------------------------------------
            # Eight weeks of trading
            # ------------------------------------------------------------------
            weighted_skus: list[str] = []
            for _cat, _name, sku, _bc, _p, _c, _u, _s, popularity in PRODUCTS:
                weighted_skus.extend([sku] * popularity)

            hours = list(HOUR_WEIGHTS)
            hour_weights = [HOUR_WEIGHTS[h] for h in hours]
            methods = [m for m, _ in PAYMENT_MIX]
            method_weights = [w for _, w in PAYMENT_MIX]

            counters: dict[str, int] = {}
            totals = {"orders": 0, "revenue": Decimal("0"), "refunds": 0}
            all_orders: list[Order] = []

            now = datetime.now(UTC)
            for day_offset in range(WEEKS_OF_HISTORY * 7 + 1):
                day = (history_start + timedelta(days=day_offset)).date()
                is_today = day == now.date()
                # Fridays and Saturdays are the busy ones; Mondays are quiet.
                weekday_factor = {0: 0.8, 1: 0.9, 2: 0.95, 3: 1.0, 4: 1.25, 5: 1.35, 6: 1.05}[
                    day.weekday()
                ]
                # A gentle upward trend, so the revenue chart has a direction.
                growth = 1 + (day_offset / (WEEKS_OF_HISTORY * 7)) * 0.35
                order_count = max(4, int(rng.gauss(26, 5) * weekday_factor * growth))
                # Today is still in progress: only the hours that have
                # actually happened, and only their share of the takings.
                day_hours = [h for h in hours if not is_today or h <= now.hour]
                if not day_hours:
                    day_hours = hours[:1]
                if is_today:
                    elapsed = sum(HOUR_WEIGHTS[h] for h in day_hours) / sum(hour_weights)
                    order_count = max(1, int(order_count * elapsed))
                day_hour_weights = [HOUR_WEIGHTS[h] for h in day_hours]

                day_shifts: dict[str, Shift] = {}
                for cashier in cashiers:
                    shift_open = (
                        min(datetime.combine(day, time(8, 0), tzinfo=UTC), now)
                        if is_today
                        else datetime.combine(day, time(8, 0), tzinfo=UTC)
                    )
                    shift = Shift(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        user_id=cashier.id,
                        status=ShiftStatus.OPEN if is_today else ShiftStatus.CLOSED,
                        opened_at=shift_open,
                        closed_at=None
                        if is_today
                        else datetime.combine(day, time(22, 0), tzinfo=UTC),
                        opening_float=Decimal("200000"),
                        created_at=shift_open,
                        updated_at=shift_open,
                    )
                    session.add(shift)
                    day_shifts[str(cashier.id)] = shift
                await session.flush()

                cash_taken: dict[str, Decimal] = {k: Decimal("0") for k in day_shifts}

                for _ in range(order_count):
                    hour = rng.choices(day_hours, weights=day_hour_weights, k=1)[0]
                    when = datetime.combine(
                        day, time(hour, rng.randrange(60), rng.randrange(60)), tzinfo=UTC
                    )
                    # The current hour is only partly over -- a sale stamped
                    # ten minutes from now would be a sale in the future.
                    if when > now:
                        when = now - timedelta(minutes=rng.randrange(1, 30))
                    cashier = rng.choice(cashiers)
                    shift = day_shifts[str(cashier.id)]

                    basket_size = rng.choices([1, 2, 3, 4, 5, 6], weights=[16, 24, 24, 18, 12, 6])[
                        0
                    ]
                    chosen: list[str] = []
                    while len(chosen) < basket_size:
                        sku = rng.choice(weighted_skus)
                        if sku not in chosen:
                            chosen.append(sku)

                    lines: list[pricing.LineInput] = []
                    for sku in chosen:
                        product = products[sku]
                        if product.unit is ProductUnit.KG:
                            qty = Decimal(str(round(rng.uniform(0.3, 2.5), 3)))
                        else:
                            qty = Decimal(rng.choices([1, 2, 3], weights=[70, 24, 6])[0])

                        # Reorder when the shelf runs low, not once it is
                        # bare. Which items end up low is decided deliberately
                        # further down, not by whatever happened to run out.
                        if stock[sku] - qty < Decimal("5"):
                            restock = Decimal(rng.randrange(60, 180))
                            stock[sku] += restock
                            session.add(
                                StockMovement(
                                    tenant_id=tenant.id,
                                    branch_id=branch.id,
                                    product_id=product.id,
                                    movement_type=StockMovementType.PURCHASE,
                                    quantity=restock,
                                    quantity_after=stock[sku],
                                    unit_cost=product.cost_price,
                                    note="Yetkazib berish",
                                    created_at=when - timedelta(hours=2),
                                    updated_at=when - timedelta(hours=2),
                                )
                            )

                        lines.append(
                            pricing.LineInput(
                                product_id=str(product.id),
                                name=product.name,
                                sku=product.sku,
                                barcode=product.barcode,
                                unit_price=product.price,
                                unit_cost=product.cost_price,
                                quantity=qty,
                                tax_rate=Decimal("0")
                                if product.tax_rate_id == zero.id
                                else Decimal("0.12"),
                                tax_inclusive=True,
                            )
                        )

                    # One basket in twenty gets a small discount.
                    discount_type = DiscountType.NONE
                    discount_value = Decimal("0")
                    if rng.random() < 0.05:
                        discount_type = DiscountType.PERCENT
                        discount_value = Decimal(rng.choice([5, 10]))

                    cart = pricing.calculate_cart(
                        lines,
                        order_discount_type=discount_type,
                        order_discount_value=discount_value,
                    )

                    period = day.strftime("%Y%m%d")
                    counters[period] = counters.get(period, 0) + 1
                    order_number = f"{branch.code}-{period}-{counters[period]:04d}"

                    method = rng.choices(methods, weights=method_weights, k=1)[0]
                    customer = rng.choice(customers) if rng.random() < 0.18 else None

                    order = Order(
                        id=uuid_lib.uuid4(),
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        cashier_id=cashier.id,
                        customer_id=customer.id if customer else None,
                        shift_id=shift.id,
                        order_number=order_number,
                        status=OrderStatus.COMPLETED,
                        subtotal=cart.subtotal,
                        discount_type=discount_type,
                        discount_value=discount_value,
                        discount_total=cart.discount_total,
                        tax_total=cart.tax_total,
                        total=cart.total,
                        paid_total=cart.total,
                        cost_total=cart.cost_total,
                        currency=tenant.currency,
                        completed_at=when,
                        created_at=when,
                        updated_at=when,
                    )
                    session.add(order)

                    for computed in cart.lines:
                        line = computed.line
                        session.add(
                            OrderItem(
                                tenant_id=tenant.id,
                                order_id=order.id,
                                product_id=uuid_lib.UUID(line.product_id),
                                product_name=line.name,
                                sku=line.sku,
                                barcode=line.barcode,
                                quantity=line.quantity,
                                unit_price=line.unit_price,
                                unit_cost=line.unit_cost,
                                discount_amount=computed.discount_amount,
                                tax_rate=line.tax_rate,
                                tax_amount=computed.tax_amount,
                                tax_inclusive=line.tax_inclusive,
                                line_total=computed.net,
                                created_at=when,
                                updated_at=when,
                            )
                        )

                        sku = line.sku
                        stock[sku] -= line.quantity
                        session.add(
                            StockMovement(
                                tenant_id=tenant.id,
                                branch_id=branch.id,
                                product_id=uuid_lib.UUID(line.product_id),
                                movement_type=StockMovementType.SALE,
                                quantity=-line.quantity,
                                quantity_after=stock[sku],
                                unit_cost=line.unit_cost,
                                reference_type="order",
                                reference_id=order.id,
                                created_by_id=cashier.id,
                                created_at=when,
                                updated_at=when,
                            )
                        )

                    tendered = None
                    change = Decimal("0")
                    if method is PaymentMethod.CASH:
                        # Round up to the next 5,000 so'm, the way a customer
                        # actually hands over notes.
                        step = Decimal("5000")
                        tendered = (cart.total / step).to_integral_value(
                            rounding="ROUND_CEILING"
                        ) * step
                        change = tendered - cart.total
                        cash_taken[str(cashier.id)] += cart.total

                    session.add(
                        Payment(
                            tenant_id=tenant.id,
                            order_id=order.id,
                            cashier_id=cashier.id,
                            method=method,
                            status=PaymentStatus.CAPTURED,
                            amount=cart.total,
                            tendered_amount=tendered,
                            change_amount=change,
                            processed_at=when,
                            created_at=when,
                            updated_at=when,
                        )
                    )

                    if customer is not None:
                        customer.order_count += 1
                        customer.total_spent += cart.total
                        customer.loyalty_points += int(cart.total / Decimal("10000"))

                    order.change_due = change
                    totals["orders"] += 1
                    totals["revenue"] += cart.total
                    all_orders.append(order)

                await session.flush()

                for cashier in cashiers:
                    shift = day_shifts[str(cashier.id)]
                    taken = cash_taken[str(cashier.id)]
                    shift.cash_in = taken
                    shift.expected_cash = shift.opening_float + taken
                    if is_today:
                        # Still open -- nothing has been counted yet.
                        continue
                    # Real tills are a few thousand so'm out; a perfect count
                    # every single day would be the unrealistic part.
                    drift = Decimal(rng.choice([0, 0, 0, -5000, -2000, 2000, 5000]))
                    shift.counted_cash = shift.expected_cash + drift
                    shift.cash_difference = drift

            # ------------------------------------------------------------------
            # A handful of refunds, so the sales screen is not uniformly happy
            # ------------------------------------------------------------------
            recent = [
                o for o in all_orders if o.completed_at > datetime.now(UTC) - timedelta(days=21)
            ]
            for order in rng.sample(recent, k=min(9, len(recent))):
                items = list(
                    await session.scalars(select(OrderItem).where(OrderItem.order_id == order.id))
                )
                if not items:
                    continue
                item = rng.choice(items)
                refund_qty = item.quantity
                share = item.line_total

                when = order.completed_at + timedelta(days=rng.randrange(1, 4))
                if when > datetime.now(UTC):
                    when = datetime.now(UTC) - timedelta(hours=3)

                item.refunded_quantity = refund_qty
                fully = len(items) == 1
                order.refunded_total = share
                order.status = OrderStatus.REFUNDED if fully else OrderStatus.PARTIALLY_REFUNDED

                session.add(
                    Refund(
                        tenant_id=tenant.id,
                        order_id=order.id,
                        created_by_id=manager.id,
                        amount=share,
                        method=PaymentMethod.CASH,
                        reason=rng.choice(
                            ["Mijoz qaytardi", "Muddati o'tgan", "Noto'g'ri tovar", "Sifatsiz"]
                        ),
                        restocked=True,
                        line_items=[
                            {
                                "order_item_id": str(item.id),
                                "quantity": str(refund_qty),
                                "amount": str(share),
                            }
                        ],
                        created_at=when,
                        updated_at=when,
                    )
                )

                if item.sku and item.sku in stock:
                    stock[item.sku] += refund_qty
                    session.add(
                        StockMovement(
                            tenant_id=tenant.id,
                            branch_id=branch.id,
                            product_id=item.product_id,
                            movement_type=StockMovementType.RETURN,
                            quantity=refund_qty,
                            quantity_after=stock[item.sku],
                            unit_cost=item.unit_cost,
                            reference_type="refund",
                            reference_id=order.id,
                            created_by_id=manager.id,
                            created_at=when,
                            updated_at=when,
                        )
                    )
                totals["refunds"] += 1

            # ------------------------------------------------------------------
            # Land the final stock levels, leaving a few items genuinely low
            # so the low-stock panel has something to say.
            # ------------------------------------------------------------------
            for sku, item in stock_items.items():
                item.quantity = stock[sku]

            for sku in ("SUT-004", "NON-004", "MAI-002", "ICH-003", "SUT-003"):
                item = stock_items[sku]
                # SUT-003 goes to nil: an empty shelf is a state the
                # inventory screen has to show, so the demo shows one.
                target = Decimal("0") if sku == "SUT-003" else Decimal(rng.randrange(3, 10))
                shortfall = item.quantity - target
                if shortfall > 0:
                    item.quantity -= shortfall
                    stock[sku] = item.quantity
                    session.add(
                        StockMovement(
                            tenant_id=tenant.id,
                            branch_id=branch.id,
                            product_id=products[sku].id,
                            movement_type=StockMovementType.WASTE,
                            quantity=-shortfall,
                            quantity_after=item.quantity,
                            unit_cost=products[sku].cost_price,
                            note="Muddati o'tgan / shikastlangan",
                        )
                    )

            await session.commit()

    summary = {
        "shop": slug,
        "products": len(PRODUCTS),
        "staff": len(STAFF) + 1,
        "orders": totals["orders"],
        "revenue": str(totals["revenue"]),
        "refunds": totals["refunds"],
    }
    logger.info("Seeded showcase data: %s", summary)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    asyncio.run(
        seed_showcase(
            args[0] if args else "demo",
            reset="--reset" in sys.argv,
        )
    )
