"""Tests for core entities and honest uncertainty."""

from knowledge_surface import (
    Confidence,
    Entity,
    EntityKind,
    Invariant,
    RelationKind,
    Relationship,
)


def test_entity_id_deterministic():
    a = Entity.make_id(EntityKind.MODULE, "foo", "a.py")
    b = Entity.make_id(EntityKind.MODULE, "foo", "a.py")
    assert a == b


def test_confidence_is_first_class():
    e = Entity(id="x", kind=EntityKind.FUNCTION, name="f", confidence=Confidence.UNKNOWN)
    assert e.confidence == Confidence.UNKNOWN
    assert e.confidence.value == "unknown"


def test_relationship_requires_existing_entities():
    from knowledge_surface import KnowledgeSurface
    ks = KnowledgeSurface()
    e = Entity(id="m", kind=EntityKind.MODULE, name="m")
    ks.add_entity(e)
    import pytest
    with pytest.raises(KeyError):
        ks.add_relationship(Relationship(
            id="r", source="m", target="missing", kind=RelationKind.IMPORTS,
        ))


def test_invariant_scope_and_severity():
    inv = Invariant(id="i", name="credit", description="d", scope=["m"], severity="error")
    assert inv.severity == "error"
    assert "m" in inv.scope
