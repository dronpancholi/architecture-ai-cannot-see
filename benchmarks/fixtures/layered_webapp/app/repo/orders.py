"""Order repository (persistence layer)."""


class OrderRepository:
    def __init__(self, db):
        self.db = db

    def insert(self, customer_id: str, amount: int) -> dict:
        row = {"id": f"o-{customer_id}", "amount": amount}
        self.db.rows.append(row)
        return row
