"""Tests for propagation and risk scoring."""

from pathlib import Path

from knowledge_surface import (
    Confidence,
    InvariantRegistry,
    PropagationAnalyzer,
    PythonASTExtractor,
    RiskScorer,
)


def build_ks():
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    ks = PythonASTExtractor(root).build()
    reg = InvariantRegistry()
    order_svc = next(e for e in ks.entities() if e.name == "OrderService")
    reg.declare(name="credit-limit", description="d", scope=[order_svc.id], severity="error", confidence=Confidence.KNOWN)
    reg.apply(ks)
    return ks, order_svc


def test_propagation_blast_radius():
    ks, svc = build_ks()
    pa = PropagationAnalyzer(ks)
    res = pa.analyze(svc.id)
    assert res.blast_radius >= 0
    assert svc.id not in res.transitive_dependents


def test_risk_scorer_range():
    ks, svc = build_ks()
    rs = RiskScorer(ks)
    r = rs.score(svc.id)
    assert 0.0 <= r.score <= 1.0
    assert r.level in {"low", "medium", "high", "critical"}


def test_risk_unknown_entity():
    ks, _ = build_ks()
    rs = RiskScorer(ks)
    r = rs.score("nope")
    assert r.score == 0.0
    assert r.level == "low"
