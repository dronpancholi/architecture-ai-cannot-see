"""Benchmark scenarios: realistic changes against realistic fixtures.

Each scenario is labelled with the ground truth: should the change be blocked?
The benchmark measures whether the semantic verifier agrees, including on
safe refactors (false-positive control) and pre-existing debt.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.rules import (
    BehavioralRule,
    ForbiddenCallRule,
    ForbiddenImportRule,
    NoMutableDefaultRule,
    NoOrphanedCallsRule,
    RequireCallRule,
    Rule,
    TypeAnnotationRule,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


@dataclass
class Scenario:
    name: str
    fixture: str
    category: str
    expected_blocked: bool
    rules: list[Rule]
    make_changes: Callable[[Path], ChangeSet]
    setup: Callable[[Path], None] | None = None


def _read(root: Path, rel: str) -> str:
    return (root / rel).read_text()


def _modify(root: Path, rel: str, old: str, new: str) -> ChangeSet:
    before = _read(root, rel)
    assert old in before, f"mutation anchor not found in {rel}: {old!r}"
    after = before.replace(old, new, 1)
    return ChangeSet(files=[FileChange(path=rel, before=before, after=after)])


def _append_call(root: Path, rel: str, anchor: str, call: str) -> ChangeSet:
    before = _read(root, rel)
    assert anchor in before
    after = before.replace(anchor, anchor + "\n        " + call, 1)
    return ChangeSet(files=[FileChange(path=rel, before=before, after=after)])


# --- rule sets --------------------------------------------------------------

def layered_rules() -> list[Rule]:
    return [
        ForbiddenImportRule(
            "layer-route-no-db", r"app/routes/.*\.py$", r"app\.db",
            "routes must not import the database layer directly",
        ),
        RequireCallRule(
            "service-authorize-first", r"^place$", "authorize", before_call="insert",
            description="order service must authorize before inserting",
        ),
    ]


def auth_rules() -> list[Rule]:
    return [
        RequireCallRule(
            "delete-authorize", r"^delete_account$", "authorize", before_call="delete",
            description="delete_account must authorize before deleting",
        ),
        RequireCallRule(
            "transfer-authorize", r"^transfer$", "authorize", before_call="move",
            description="transfer must authorize before moving funds",
        ),
        NoMutableDefaultRule(),
        TypeAnnotationRule("public-annotated"),
    ]


def pricing_rules() -> list[Rule]:
    return [
        ForbiddenCallRule("no-float", r"pricing/engine\.py$", "float",
                          "pricing engine must use Decimal/Money, not float"),
        BehavioralRule(
            "non-negative-total",
            """
from decimal import Decimal
from pricing.engine import total
from pricing.money import Money

def check():
    t = total([(Money(Decimal("10")), 1)], discount=Decimal("20"))
    assert t.amount >= 0, f"negative total: {t.amount}"
""",
            "totals must never be negative",
        ),
    ]


def plugin_rules() -> list[Rule]:
    return [
        ForbiddenImportRule(
            "registry-no-importlib", r"host/registry\.py$", r"importlib",
            "registry must delegate dynamic imports to PluginLoader",
        ),
        ForbiddenCallRule("registry-no-eval", r"host/registry\.py$", "eval",
                          "registry must not eval"),
        ForbiddenCallRule("registry-no-exec", r"host/registry\.py$", "exec",
                          "registry must not exec"),
    ]


# --- scenarios --------------------------------------------------------------

def scenarios() -> list[Scenario]:
    out: list[Scenario] = []

    # Layered webapp
    out.append(Scenario(
        "layer-violation-direct-db", "layered_webapp", "introduced-violation", True,
        layered_rules(),
        lambda r: _modify(
            r, "app/routes/orders.py",
            "from app.services.orders import OrderService",
            "from app.db import Database\nfrom app.services.orders import OrderService",
        ),
    ))
    def safe_rename(r: Path) -> ChangeSet:
        before = _read(r, "app/routes/orders.py")
        after = (
            before.replace("order = service.place", "created = service.place")
            .replace('order["id"]', 'created["id"]')
            .replace('order["amount"]', 'created["amount"]')
        )
        return ChangeSet(files=[FileChange(path="app/routes/orders.py", before=before, after=after)])

    out.append(Scenario(
        "layer-safe-rename", "layered_webapp", "safe-refactor", False,
        layered_rules(), safe_rename,
    ))
    out.append(Scenario(
        "layer-violation-auth-order", "layered_webapp", "introduced-violation", True,
        layered_rules(),
        lambda r: _modify(
            r, "app/services/orders.py",
            "        self.authorize(customer_id)\n        return self.repo.insert(customer_id, amount)",
            "        return self.repo.insert(customer_id, amount)\n        self.authorize(customer_id)",
        ),
    ))
    out.append(Scenario(
        "layer-safe-add-method", "layered_webapp", "safe-refactor", False,
        layered_rules(),
        lambda r: _modify(
            r, "app/services/orders.py",
            "    def authorize(self, customer_id: str) -> None:",
            "    def describe(self, customer_id: str) -> str:\n        return f'customer:{customer_id}'\n\n    def authorize(self, customer_id: str) -> None:",
        ),
    ))
    out.append(Scenario(
        "layer-orphaned-calls", "layered_webapp", "introduced-violation", True,
        layered_rules() + [NoOrphanedCallsRule()],
        lambda r: _modify(
            r, "app/repo/orders.py",
            "    def insert(self, customer_id: str, amount: int) -> dict:\n        row = {\"id\": f\"o-{customer_id}\", \"amount\": amount}\n        self.db.rows.append(row)\n        return row",
            "    pass",
        ),
    ))
    out.append(Scenario(
        "layer-preexisting-debt", "layered_webapp", "preexisting-debt", False,
        layered_rules(),
        lambda r: _modify(
            r, "app/services/orders.py",
            '"""Order service (business layer)."""',
            '"""Order service (business layer)."""\n\n# audit: touched',
        ),
        setup=lambda r: (r / "app/routes/audit.py").write_text(
            "from app.db import Database\n\n\ndef ping(db: Database) -> None:\n    db.execute('select 1')\n"
        ),
    ))

    # Auth service
    out.append(Scenario(
        "auth-missing-authorize-delete", "auth_service", "introduced-violation", True,
        auth_rules(),
        lambda r: _modify(
            r, "auth/service.py",
            "        self.authorize(actor, \"delete\")\n        return self.repo.delete(user_id)",
            "        return self.repo.delete(user_id)",
        ),
    ))
    out.append(Scenario(
        "auth-missing-authorize-transfer", "auth_service", "introduced-violation", True,
        auth_rules(),
        lambda r: _modify(
            r, "auth/service.py",
            "        self.authorize(actor, \"transfer\")\n        return self.repo.move(src, dst, amount)",
            "        return self.repo.move(src, dst, amount)",
        ),
    ))
    out.append(Scenario(
        "auth-safe-logging", "auth_service", "safe-refactor", False,
        auth_rules(),
        lambda r: _modify(
            r, "auth/service.py",
            "    def authorize(self, actor: str, action: str) -> None:",
            "    def audit(self, actor: str, action: str) -> str:\n        return f'{actor}:{action}'\n\n    def authorize(self, actor: str, action: str) -> None:",
        ),
    ))
    out.append(Scenario(
        "auth-mutable-default", "auth_service", "introduced-violation", True,
        auth_rules(),
        lambda r: _modify(
            r, "auth/service.py",
            "    def authorize(self, actor: str, action: str) -> None:",
            "    def log(self, entries: list = []) -> None:\n        entries.append('x')\n\n    def authorize(self, actor: str, action: str) -> None:",
        ),
    ))
    out.append(Scenario(
        "auth-missing-annotation", "auth_service", "introduced-violation", True,
        auth_rules(),
        lambda r: _modify(
            r, "auth/service.py",
            "    def authorize(self, actor: str, action: str) -> None:",
            "    def ping(self, actor):\n        return actor\n\n    def authorize(self, actor: str, action: str) -> None:",
        ),
    ))

    # Pricing
    out.append(Scenario(
        "pricing-float-regression", "pricing_engine", "introduced-violation", True,
        pricing_rules(),
        lambda r: _modify(
            r, "pricing/engine.py",
            "    return Money(unit_price.amount * quantity, unit_price.currency)",
            "    return Money(float(unit_price.amount) * quantity, unit_price.currency)",
        ),
    ))
    out.append(Scenario(
        "pricing-negative-total", "pricing_engine", "introduced-violation", True,
        pricing_rules(),
        lambda r: _modify(
            r, "pricing/engine.py",
            "    if result.amount < 0:\n        return zero()\n    return result",
            "    return result",
        ),
    ))
    out.append(Scenario(
        "pricing-safe-refactor", "pricing_engine", "safe-refactor", False,
        pricing_rules(),
        lambda r: _modify(
            r, "pricing/engine.py",
            "    acc = zero()\n    for price, qty in lines:\n        acc = acc.plus(line_total(price, qty))",
            "    acc = zero()\n    for price, qty in lines:\n        line = line_total(price, qty)\n        acc = acc.plus(line)",
        ),
    ))

    # Plugin host
    out.append(Scenario(
        "plugin-registry-importlib", "plugin_host", "introduced-violation", True,
        plugin_rules(),
        lambda r: _modify(
            r, "host/registry.py",
            "from host.loader import PluginLoader",
            "import importlib\nfrom host.loader import PluginLoader",
        ),
    ))
    out.append(Scenario(
        "plugin-registry-eval", "plugin_host", "introduced-violation", True,
        plugin_rules(),
        lambda r: _modify(
            r, "host/registry.py",
            "    def install(self, name: str) -> None:",
            "    def unsafe(self, code: str):\n        return eval(code)\n\n    def install(self, name: str) -> None:",
        ),
    ))
    out.append(Scenario(
        "plugin-safe-logging", "plugin_host", "safe-refactor", False,
        plugin_rules(),
        lambda r: _modify(
            r, "host/registry.py",
            "    def install(self, name: str) -> None:",
            "    def describe(self, name: str) -> str:\n        return f'plugin:{name}'\n\n    def install(self, name: str) -> None:",
        ),
    ))

    return out
