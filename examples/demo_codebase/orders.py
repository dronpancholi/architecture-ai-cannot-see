"""Order processing domain.

INVARIANT: an order's total must never exceed the customer's credit limit
"""

from dataclasses import dataclass
from decimal import Decimal


@dataclass
class Customer:
    id: str
    name: str
    credit_limit: Decimal


@dataclass
class Order:
    id: str
    customer_id: str
    amount: Decimal


class OrderService:
    """Processes orders. The credit-limit check is enforced by review culture,
    not by code (intentionally, to demonstrate the Second Architecture)."""

    def __init__(self, customers: dict[str, Customer]):
        self.customers = customers
        self.orders: dict[str, Order] = {}

    def place_order(self, order: Order) -> Order:
        # NOTE: no credit check here on purpose (invariant lives nowhere).
        self.orders[order.id] = order
        return order

    def total_for(self, customer_id: str) -> Decimal:
        return sum((o.amount for o in self.orders.values() if o.customer_id == customer_id), Decimal("0"))
