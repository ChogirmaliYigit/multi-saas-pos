"""Cart arithmetic.

Every value here is a Decimal. Floats are never used for money anywhere in
this codebase: 0.1 + 0.2 != 0.3 in binary floating point, and a till that is
one cent out at the end of a shift is a till that gets counted three times.

The client computes the same figures to render a live cart, but these are the
authoritative ones -- the server never trusts a total that arrived over the
wire.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from app.models.enums import DiscountType

CENTS = Decimal("0.01")
QTY = Decimal("0.001")
ZERO = Decimal("0.00")


def money(value: Decimal | str | int) -> Decimal:
    """Round to 2dp, half-up.

    Banker's rounding (Python's default) would send half-cents to the nearest
    even value, which is defensible statistically and indefensible to a shop
    owner comparing a receipt against a calculator.
    """
    return Decimal(value).quantize(CENTS, rounding=ROUND_HALF_UP)


def quantity(value: Decimal | str | int) -> Decimal:
    return Decimal(value).quantize(QTY, rounding=ROUND_HALF_UP)


@dataclass(slots=True)
class LineInput:
    product_id: str
    name: str
    sku: str | None
    barcode: str | None
    unit_price: Decimal
    unit_cost: Decimal
    quantity: Decimal
    tax_rate: Decimal = ZERO
    tax_inclusive: bool = False
    discount_type: DiscountType = DiscountType.NONE
    discount_value: Decimal = ZERO


@dataclass(slots=True)
class LineTotals:
    line: LineInput
    gross: Decimal = ZERO  # unit_price * quantity, before any discount
    discount_amount: Decimal = ZERO  # line discount + share of order discount
    net: Decimal = ZERO  # what the customer pays for this line
    tax_amount: Decimal = ZERO
    cost: Decimal = ZERO

    @property
    def taxable_base(self) -> Decimal:
        """Net excluding tax -- differs by inclusive/exclusive."""
        return self.net - self.tax_amount if self.line.tax_inclusive else self.net


@dataclass(slots=True)
class CartTotals:
    lines: list[LineTotals] = field(default_factory=list)
    subtotal: Decimal = ZERO
    discount_total: Decimal = ZERO
    tax_total: Decimal = ZERO
    total: Decimal = ZERO
    cost_total: Decimal = ZERO
    rounding_adjustment: Decimal = ZERO


def _line_discount(gross: Decimal, kind: DiscountType, value: Decimal) -> Decimal:
    if kind is DiscountType.PERCENT:
        capped = min(max(value, ZERO), Decimal(100))
        return money(gross * capped / Decimal(100))
    if kind is DiscountType.FIXED:
        # Never let a discount exceed the line, which would create a negative
        # line and a refund the cashier did not intend.
        return money(min(max(value, ZERO), gross))
    return ZERO


def _allocate_order_discount(lines: list[LineTotals], discount: Decimal) -> None:
    """Spread an order-level discount across lines in proportion to value.

    It has to land on the lines rather than being subtracted at the end,
    because each line may carry a different tax rate -- a flat deduction from
    the footer would tax the customer on money they did not pay.

    Proportional shares rarely sum to the target exactly, so the rounding
    remainder is pushed onto the largest line.
    """
    if discount <= ZERO:
        return

    base = sum((line.net for line in lines), ZERO)
    if base <= ZERO:
        return

    discount = min(discount, base)
    allocated = ZERO
    shares: list[Decimal] = []

    for line in lines:
        share = money(discount * line.net / base)
        shares.append(share)
        allocated += share

    remainder = discount - allocated
    if remainder != ZERO:
        biggest = max(range(len(lines)), key=lambda i: lines[i].net)
        shares[biggest] += remainder

    for line, share in zip(lines, shares, strict=True):
        line.discount_amount += share
        line.net -= share


def _tax_for(net: Decimal, rate: Decimal, inclusive: bool) -> Decimal:
    if rate <= ZERO:
        return ZERO
    if inclusive:
        # The shelf price already contains the tax, so extract it:
        #   tax = net - net / (1 + rate)
        return money(net - (net / (Decimal(1) + rate)))
    return money(net * rate)


def calculate_cart(
    lines: list[LineInput],
    *,
    order_discount_type: DiscountType = DiscountType.NONE,
    order_discount_value: Decimal = ZERO,
    cash_rounding: Decimal | None = None,
) -> CartTotals:
    """Compute a whole cart.

    Order of operations matters and is not arbitrary:
      1. line gross
      2. line discount
      3. order discount, allocated across lines
      4. tax, per line, on the post-discount net
      5. optional cash rounding on the grand total

    Taxing before discounting would overcharge; discounting after tax would
    make the tax line wrong on the receipt, which is the number a tax audit
    actually looks at.
    """
    totals = CartTotals()

    for line in lines:
        gross = money(line.unit_price * line.quantity)
        discount = _line_discount(gross, line.discount_type, line.discount_value)
        computed = LineTotals(
            line=line,
            gross=gross,
            discount_amount=discount,
            net=gross - discount,
            cost=money(line.unit_cost * line.quantity),
        )
        totals.lines.append(computed)

    subtotal_after_line_discounts = sum((line.net for line in totals.lines), ZERO)

    order_discount = ZERO
    if order_discount_type is DiscountType.PERCENT:
        order_discount = money(
            subtotal_after_line_discounts
            * min(max(order_discount_value, ZERO), Decimal(100))
            / Decimal(100)
        )
    elif order_discount_type is DiscountType.FIXED:
        order_discount = money(min(max(order_discount_value, ZERO), subtotal_after_line_discounts))

    _allocate_order_discount(totals.lines, order_discount)

    for computed in totals.lines:
        computed.tax_amount = _tax_for(
            computed.net, computed.line.tax_rate, computed.line.tax_inclusive
        )

    totals.subtotal = sum((line.gross for line in totals.lines), ZERO)
    totals.discount_total = sum((line.discount_amount for line in totals.lines), ZERO)
    totals.tax_total = sum((line.tax_amount for line in totals.lines), ZERO)
    totals.cost_total = sum((line.cost for line in totals.lines), ZERO)

    # Inclusive tax is already inside net; exclusive tax is added on top.
    net_total = sum((line.net for line in totals.lines), ZERO)
    exclusive_tax = sum(
        (line.tax_amount for line in totals.lines if not line.line.tax_inclusive),
        ZERO,
    )
    total = net_total + exclusive_tax

    if cash_rounding and cash_rounding > ZERO:
        # Countries that have withdrawn small coins round the cash total to
        # the smallest denomination still in circulation.
        rounded = (total / cash_rounding).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        ) * cash_rounding
        totals.rounding_adjustment = money(rounded - total)
        total = money(rounded)

    totals.total = money(total)
    return totals
