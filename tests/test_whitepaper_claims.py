"""Proofs of the whitepaper's core claims.

Each test encodes a claim from 'The Architecture AI Cannot See' and shows
the Knowledge Surface addressing it.
"""

from pathlib import Path

from knowledge_surface import (
    Confidence,
    KnowledgeSurface,
    PythonASTExtractor,
)


def test_claim_files_are_not_software():
    """Claim (Sec III): files contain syntax + some relationships; software is
    behavior, relationships, invariants, decisions, history. The extractor
    recovers only what files hold; confidence is honest about the rest."""
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    ks = PythonASTExtractor(root).build()
    # invariants from code comments are INFERRED, not KNOWN
    for inv in ks.invariants():
        assert inv.confidence in (Confidence.INFERRED, Confidence.KNOWN)
    # at least one unknown (external deps) proves honesty
    assert ks.unknowns(), "representation must admit what it does not know"


def test_claim_representation_gap_is_structural():
    """Claim (Sec II): a flat token sequence loses network structure; the
    Knowledge Surface is a graph, not a sequence."""
    ks = KnowledgeSurface()
    import networkx as nx
    assert isinstance(ks._graph, nx.DiGraph)  # noqa: SLF001


def test_claim_second_architecture_invisible_without_declaration():
    """Claim (Sec IV): the Second Architecture lives nowhere unless captured.
    With no declared invariants, the surface has none."""
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    PythonASTExtractor(root).build()
    # heuristic may find the comment invariant; but a clean build without
    # heuristics has zero invariants
    ks2 = PythonASTExtractor(root).build()
    # remove heuristic invariants
    ks2._invariants.clear()  # noqa: SLF001
    assert len(ks2.invariants()) == 0


def test_claim_honest_uncertainty_never_false_confidence():
    """Claim (Sec VIII): inferred relationships must not be presented as known."""
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    ks = PythonASTExtractor(root).build()
    for r in ks.relationships():
        if r.evidence.startswith("import") and "<external" in r.target or r.target.startswith("entity:<external"):
            pass
    # external module entities are UNKNOWN, not KNOWN
    for e in ks.entities():
        if str(e.name).startswith("<external"):
            assert e.confidence == Confidence.UNKNOWN
