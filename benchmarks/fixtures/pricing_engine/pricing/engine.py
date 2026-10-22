"""Pricing engine. Invariant: totals are Money and never negative."""

from decimal import Decimal

from pricing.money import Money, zero


def line_total(unit_price: Money, quantity: int) -> Money:
    return Money(unit_price.amount * quantity, unit_price.currency)


def total(lines: list[tuple[Money, int]], discount: Decimal = Decimal("0")) -> Money:
    acc = zero()
    for price, qty in lines:
        acc = acc.plus(line_total(price, qty))
    result = Money(acc.amount - discount, acc.currency)
    if result.amount < 0:
        return zero()
    return result
