"""Account persistence."""


class AccountRepository:
    def __init__(self, db):
        self.db = db

    def delete(self, user_id: str) -> bool:
        self.db.users.pop(user_id, None)
        return True

    def move(self, src: str, dst: str, amount: int) -> bool:
        if src not in self.db.users or dst not in self.db.users:
            return False
        if self.db.users[src] < amount:
            return False
        self.db.users[src] -= amount
        self.db.users[dst] += amount
        return True
