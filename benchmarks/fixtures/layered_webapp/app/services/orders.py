"""Order service (business layer)."""

from app.repo.orders import OrderRepository


class OrderService:
    def __init__(self, repo: OrderRepository):
        self.repo = repo

    def place(self, customer_id: str, amount: int) -> dict:
        self.authorize(customer_id)
        return self.repo.insert(customer_id, amount)

    def authorize(self, customer_id: str) -> None:
        if not customer_id:
            raise PermissionError("missing customer")
