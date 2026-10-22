"""Money representation - version B (used by reporting).

A second, slightly different representation of the same concept.
This is the seed of semantic drift: two 'Money' types, two add() semantics.
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Money:
    value: Decimal
    ccy: str = "USD"

    def plus(self, other: "Money") -> "Money":
        if self.ccy != other.ccy:
            return Money(self.value + other.value, "MIXED")
        return Money(self.value + other.value, self.ccy)
