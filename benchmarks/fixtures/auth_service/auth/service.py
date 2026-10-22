"""Account service with an authorization invariant."""

from auth.repo import AccountRepository


class AccountService:
    def __init__(self, repo: AccountRepository):
        self.repo = repo

    def delete_account(self, user_id: str, actor: str) -> bool:
        self.authorize(actor, "delete")
        return self.repo.delete(user_id)

    def transfer(self, src: str, dst: str, amount: int, actor: str) -> bool:
        self.authorize(actor, "transfer")
        return self.repo.move(src, dst, amount)

    def authorize(self, actor: str, action: str) -> None:
        if actor != "admin":
            raise PermissionError(f"{actor} may not {action}")
