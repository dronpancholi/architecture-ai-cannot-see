"""Money representation - version A (used by billing)."""

from decimal import Decimal


class Money:
    """Amount in a currency."""

    def __init__(self, amount: Decimal, currency: str = "USD"):
        self.amount = amount
        self.currency = currency

    def add(self, other: "Money") -> "Money":
        if self.currency != other.currency:
            raise ValueError("currency mismatch")
        return Money(self.amount + other.amount, self.currency)
