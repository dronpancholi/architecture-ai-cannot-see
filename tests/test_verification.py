"""Tests for semantic verification: rules, regression logic, false positives."""

from pathlib import Path

from knowledge_surface import (
    Allowlist,
    BehavioralRule,
    ChangeSet,
    FileChange,
    ForbiddenImportRule,
    RequireCallRule,
    SemanticVerifier,
)
from knowledge_surface.verification.change import ChangeSet as CS
from knowledge_surface.verification.rules import RuleContext

FIX = Path(__file__).resolve().parents[1] / "benchmarks" / "fixtures"


def _change(root: Path, rel: str, old: str, new: str) -> ChangeSet:
    before = (root / rel).read_text()
    assert old in before
    return ChangeSet(files=[FileChange(path=rel, before=before, after=before.replace(old, new, 1))])


def test_introduced_violation_blocked():
    root = FIX / "layered_webapp"
    changes = _change(root, "app/routes/orders.py",
                      "from app.services.orders import OrderService",
                      "from app.db import Database\nfrom app.services.orders import OrderService")
    rules = [ForbiddenImportRule("layer", r"app/routes/.*\.py$", r"app\.db")]
    report = SemanticVerifier(rules).verify(root, changes)
    assert not report.approved
    assert report.findings[0].introduced


def test_safe_change_approved():
    root = FIX / "layered_webapp"
    changes = _change(root, "app/routes/orders.py", "order = service.place", "created = service.place")
    rules = [ForbiddenImportRule("layer", r"app/routes/.*\.py$", r"app\.db")]
    report = SemanticVerifier(rules).verify(root, changes)
    assert report.approved
    assert not report.findings


def test_preexisting_debt_not_blocking():
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        shutil.copytree(FIX / "layered_webapp", root)
        (root / "app/routes/legacy.py").write_text("from app.db import Database\n")
        # unrelated change: before_tree already contains the violation
        changes = _change(root, "app/services/orders.py",
                          '"""Order service (business layer)."""',
                          '"""Order service (business layer)."""\n')
        rules = [ForbiddenImportRule("layer", r"app/routes/.*\.py$", r"app\.db")]
        report = SemanticVerifier(rules).verify(root, changes)
        assert report.approved, report.summary()
        assert report.preexisting, "preexisting debt should be reported, not blocking"


def test_allowlist_suppresses():
    root = FIX / "layered_webapp"
    changes = _change(root, "app/routes/orders.py",
                      "from app.services.orders import OrderService",
                      "from app.db import Database\nfrom app.services.orders import OrderService")
    rules = [ForbiddenImportRule("layer", r"app/routes/.*\.py$", r"app\.db")]
    report = SemanticVerifier(rules, Allowlist([("layer", "app/routes/orders.py")])).verify(root, changes)
    assert report.approved
    assert report.suppressed


def test_require_call_owner_scoping():
    import ast

    from knowledge_surface.verification.rules import _iter_functions
    tree = ast.parse("""
class A:
    def verify(self):
        return compare_digest(x, y)
class B:
    def verify(self):
        return x == y
""")
    owners = {owner for owner, _ in _iter_functions(tree)}
    assert owners == {"A", "B"}
    # rule scoped to A passes; scoped to B fails
    from knowledge_surface.verification.change import ChangeSet
    from knowledge_surface.verification.engine import _build_from_tree
    surface = _build_from_tree({"m.py": ast.unparse(tree)}, "x")
    ctx = RuleContext(before=surface, after=surface, changes=ChangeSet(), before_tree={"m.py": ast.unparse(tree)}, after_tree={"m.py": ast.unparse(tree)})
    assert RequireCallRule("r", r"^verify$", "compare_digest", owner=r"^A$").evaluate(ctx).passed
    assert not RequireCallRule("r", r"^verify$", "compare_digest", owner=r"^B$").evaluate(ctx).passed


def test_behavioral_rule_catches_negative_total():
    root = FIX / "pricing_engine"
    before = (root / "pricing/engine.py").read_text()
    after = before.replace("    if result.amount < 0:\n        return zero()\n    return result", "    return result")
    snippet = """
from decimal import Decimal
from pricing.engine import total
from pricing.money import Money

def check():
    t = total([(Money(Decimal("10")), 1)], discount=Decimal("20"))
    assert t.amount >= 0, f"negative total: {t.amount}"
"""
    report = SemanticVerifier([BehavioralRule("nonneg", snippet, trusted=True)]).verify(
        root, ChangeSet(files=[FileChange(path="pricing/engine.py", before=before, after=after)]))
    assert not report.approved
    assert "negative" in report.findings[0].message.lower()


def test_patch_parsing(tmp_path):
    root = tmp_path / "repo"
    (root / "app").mkdir(parents=True)
    (root / "app/x.py").write_text("import os\nx = 1\n")
    patch = """diff --git a/app/x.py b/app/x.py
--- a/app/x.py
+++ b/app/x.py
@@ -1,2 +1,2 @@
 import os
-x = 1
+x = 2
"""
    cs = CS.from_patch(patch, root=root)
    assert len(cs.files) == 1
    assert cs.files[0].path == "app/x.py"
    assert cs.files[0].after == "import os\nx = 2\n"
