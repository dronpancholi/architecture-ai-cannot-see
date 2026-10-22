"""Tests for KnowledgeSurface graph + serialization."""

from pathlib import Path

from knowledge_surface import (
    Confidence,
    Entity,
    EntityKind,
    KnowledgeSurface,
    PythonASTExtractor,
    RelationKind,
    Relationship,
)


def make_ks():
    ks = KnowledgeSurface(name="t")
    a = Entity(id="a", kind=EntityKind.MODULE, name="a")
    b = Entity(id="b", kind=EntityKind.MODULE, name="b")
    ks.add_entity(a)
    ks.add_entity(b)
    ks.add_relationship(Relationship(id="r", source="a", target="b", kind=RelationKind.DEPENDS_ON))
    return ks, a, b


def test_dependents_transitive():
    ks, a, b = make_ks()
    c = Entity(id="c", kind=EntityKind.MODULE, name="c")
    ks.add_entity(c)
    ks.add_relationship(Relationship(id="r2", source="c", target="a", kind=RelationKind.DEPENDS_ON))
    assert "c" in ks.dependents("a")
    assert "a" not in ks.dependents("a")


def test_serialization_roundtrip():
    ks, a, b = make_ks()
    data = ks.to_dict()
    ks2 = KnowledgeSurface.from_dict(data)
    assert ks2.stats()["entities"] == 2
    assert ks2.entity("a") is not None


def test_unknowns_surface():
    ks = KnowledgeSurface()
    ks.add_entity(Entity(id="x", kind=EntityKind.MODULE, name="x", confidence=Confidence.UNKNOWN))
    assert any("x" in u for u in ks.unknowns())


def test_extractor_builds_surface():
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    ks = PythonASTExtractor(root).build()
    assert ks.stats()["entities"] > 0
    assert any(e.name == "OrderService" for e in ks.entities())
    # honest: external imports are unknown
    assert any(e.confidence == Confidence.UNKNOWN for e in ks.entities())
