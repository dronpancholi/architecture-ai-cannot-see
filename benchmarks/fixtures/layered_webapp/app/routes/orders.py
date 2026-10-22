"""Order routes (HTTP layer)."""

from app.services.orders import OrderService


def create_order(service: OrderService, customer_id: str, amount: int) -> dict:
    order = service.place(customer_id, amount)
    return {"id": order["id"], "amount": order["amount"]}
