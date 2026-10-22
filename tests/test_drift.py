"""Tests for semantic drift detection."""

from pathlib import Path

from knowledge_surface import HeuristicInvariantExtractor, PythonASTExtractor, SemanticDriftDetector


def _build(root, sub):
    ks = PythonASTExtractor(root / "examples" / sub).build()
    HeuristicInvariantExtractor(root / "examples" / sub).extract(ks)
    return ks


def test_drift_detects_invariant_loss():
    root = Path(__file__).resolve().parents[1]
    before = _build(root, "demo_codebase")
    after = _build(root, "demo_codebase_v2")
    rep = SemanticDriftDetector(before, after).detect()
    assert rep.has_drift
    kinds = {f.kind for f in rep.findings}
    assert "invariant-loss" in kinds


def test_drift_detects_duplicate_concept():
    root = Path(__file__).resolve().parents[1]
    before = _build(root, "demo_codebase")
    after = _build(root, "demo_codebase_v2")
    rep = SemanticDriftDetector(before, after).detect()
    assert "duplicate-concept" in {f.kind for f in rep.findings}


def test_no_drift_identical():
    root = Path(__file__).resolve().parents[1]
    a = _build(root, "demo_codebase")
    b = _build(root, "demo_codebase")
    rep = SemanticDriftDetector(a, b).detect()
    assert "invariant-loss" not in {f.kind for f in rep.findings}
    assert "confidence-regression" not in {f.kind for f in rep.findings}
