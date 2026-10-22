"""Tiny in-memory database."""


class Database:
    def __init__(self):
        self.rows = []

    def execute(self, sql: str) -> None:
        self.rows.append({"sql": sql})
