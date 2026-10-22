"""Tests for the Reasoning Layer: consistency and inversion of burden of proof."""

from pathlib import Path

from knowledge_surface import (
    ChangeEvaluator,
    Confidence,
    ConsistencyChecker,
    InvariantRegistry,
    PythonASTExtractor,
)


def build_ks():
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    ks = PythonASTExtractor(root).build()
    reg = InvariantRegistry()
    order_svc = next(e for e in ks.entities() if e.name == "OrderService")
    reg.declare(
        name="credit-limit",
        description="order total must not exceed credit limit",
        scope=[order_svc.id],
        severity="error",
        confidence=Confidence.KNOWN,
    )
    reg.apply(ks)
    return ks, order_svc


def test_remove_load_bearing_entity_blocked():
    ks, svc = build_ks()
    ev = ChangeEvaluator(ks)
    va = ev.evaluate_remove_entity(svc.id)
    assert va.approved is False
    assert any(v.severity == "error" for v in va.verdict.violations)


def test_remove_unknown_entity_blocked():
    ks, _ = build_ks()
    ev = ChangeEvaluator(ks)
    va = ev.evaluate_remove_entity("does-not-exist")
    assert va.approved is False


def test_add_duplicate_entity_blocked():
    ks, svc = build_ks()
    from knowledge_surface import Entity
    dup = Entity(id="dup", kind=svc.kind, name=svc.name)
    checker = ConsistencyChecker(ks)
    v = checker.check_add_entity(dup)
    assert v.consistent is False


def test_change_touching_invariant_requires_review():
    ks, svc = build_ks()
    ev = ChangeEvaluator(ks)
    va = ev.evaluate_change("refactor order service", [svc.id])
    assert va.approved is False
    assert va.verdict.violations
