"""The cart maths. Every assertion here is a number a customer would dispute."""

from __future__ import annotations

from decimal import Decimal

from app.models.enums import DiscountType
from app.services.pricing import LineInput, calculate_cart

D = Decimal


def line(price, qty=1, *, rate="0", inclusive=False, disc=DiscountType.NONE, dv="0", cost="0"):
    return LineInput(
        product_id="p",
        name="Item",
        sku="SKU",
        barcode=None,
        unit_price=D(price),
        unit_cost=D(cost),
        quantity=D(qty),
        tax_rate=D(rate),
        tax_inclusive=inclusive,
        discount_type=disc,
        discount_value=D(dv),
    )


def test_simple_cart_without_tax():
    totals = calculate_cart([line("2.50", 3), line("1.20", 2)])
    assert totals.subtotal == D("9.90")
    assert totals.tax_total == D("0.00")
    assert totals.total == D("9.90")


def test_exclusive_tax_is_added_on_top():
    totals = calculate_cart([line("10.00", 1, rate="0.20")])
    assert totals.tax_total == D("2.00")
    assert totals.total == D("12.00")


def test_inclusive_tax_is_extracted_not_added():
    """A shelf price of 12.00 at 20% inclusive means 10.00 net + 2.00 tax --
    the customer still pays exactly 12.00."""
    totals = calculate_cart([line("12.00", 1, rate="0.20", inclusive=True)])
    assert totals.tax_total == D("2.00")
    assert totals.total == D("12.00")


def test_percent_line_discount_applies_before_tax():
    totals = calculate_cart([line("100.00", 1, rate="0.10", disc=DiscountType.PERCENT, dv="10")])
    assert totals.discount_total == D("10.00")
    # Tax is charged on 90, not on 100.
    assert totals.tax_total == D("9.00")
    assert totals.total == D("99.00")


def test_fixed_discount_cannot_exceed_the_line():
    """Otherwise a fat-fingered discount turns a sale into a refund."""
    totals = calculate_cart([line("5.00", 1, disc=DiscountType.FIXED, dv="500")])
    assert totals.discount_total == D("5.00")
    assert totals.total == D("0.00")


def test_percent_discount_is_capped_at_100():
    totals = calculate_cart([line("5.00", 1, disc=DiscountType.PERCENT, dv="250")])
    assert totals.total == D("0.00")


def test_order_discount_is_allocated_across_lines_by_value():
    totals = calculate_cart(
        [line("30.00"), line("70.00")],
        order_discount_type=DiscountType.FIXED,
        order_discount_value=D("10.00"),
    )
    assert [line.discount_amount for line in totals.lines] == [D("3.00"), D("7.00")]
    assert totals.total == D("90.00")


def test_order_discount_allocation_never_loses_a_cent():
    """Three equal lines and a 10.00 discount: 3.33 each leaves 0.01 stranded.
    It must land somewhere, not vanish."""
    totals = calculate_cart(
        [line("10.00"), line("10.00"), line("10.00")],
        order_discount_type=DiscountType.FIXED,
        order_discount_value=D("10.00"),
    )
    assert totals.discount_total == D("10.00")
    assert sum(line.discount_amount for line in totals.lines) == D("10.00")
    assert totals.total == D("20.00")


def test_order_discount_with_mixed_tax_rates_taxes_each_line_correctly():
    """The reason order discounts are allocated to lines rather than deducted
    at the footer: two rates cannot share one deduction."""
    totals = calculate_cart(
        [line("100.00", rate="0.20"), line("100.00", rate="0.05")],
        order_discount_type=DiscountType.PERCENT,
        order_discount_value=D("10"),
    )
    taxes = [line.tax_amount for line in totals.lines]
    assert taxes == [D("18.00"), D("4.50")]  # 90 * 0.20, 90 * 0.05
    assert totals.total == D("202.50")


def test_weighed_goods_use_three_decimal_quantities():
    totals = calculate_cart([line("4.00", "0.256")])  # 256 g at 4.00/kg
    assert totals.total == D("1.02")


def test_cash_rounding_to_five_cents():
    totals = calculate_cart([line("9.99", 1)], cash_rounding=D("0.05"))
    assert totals.total == D("10.00")
    assert totals.rounding_adjustment == D("0.01")


def test_totals_reconcile_for_a_realistic_basket():
    """Belt and braces: whatever the mix, subtotal - discount + exclusive tax
    must equal the total, or the receipt will not add up."""
    totals = calculate_cart(
        [
            line("3.49", 2, rate="0.20"),
            line("12.00", 1, rate="0.20", inclusive=True),
            line("0.99", 5, rate="0", disc=DiscountType.PERCENT, dv="15"),
            line("4.00", "1.350", rate="0.05"),
        ],
        order_discount_type=DiscountType.PERCENT,
        order_discount_value=D("5"),
    )
    net = sum(line.net for line in totals.lines)
    exclusive_tax = sum(line.tax_amount for line in totals.lines if not line.line.tax_inclusive)
    assert totals.total == net + exclusive_tax
    assert totals.subtotal - totals.discount_total == net


def test_empty_cart_is_zero_not_an_error():
    totals = calculate_cart([])
    assert totals.total == D("0.00")
    assert totals.lines == []
