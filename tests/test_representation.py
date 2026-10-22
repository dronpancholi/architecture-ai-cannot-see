"""Representation schema: validation, determinism, and code-only graphs."""

from __future__ import annotations

import json

import pytest

from knowledge_surface.representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    Invariant,
    Provenance,
    RelationKind,
    Relationship,
)
from knowledge_surface.representation.knowledge_surface import (
    SCHEMA_VERSION,
    KnowledgeSurface,
    SchemaError,
)


def _entity(name: str, kind: EntityKind = EntityKind.MODULE, file: str = "m.py") -> Entity:
    return Entity(
        id=Entity.make_id(kind, name, file),
        kind=kind,
        name=name,
        confidence=Confidence.KNOWN,
        provenance=Provenance(created_by="test", source=file),
    )


def _surface() -> KnowledgeSurface:
    ks = KnowledgeSurface(name="demo")
    a = ks.add_entity(_entity("a"))
    b = ks.add_entity(_entity("b"))
    ks.add_relationship(Relationship(
        id=Relationship.make_id(a.id, RelationKind.IMPORTS, b.id),
        source=a.id, target=b.id, kind=RelationKind.IMPORTS,
    ))
    ks.add_invariant(Invariant(
        id=Invariant.make_id("no-cycles"), name="no-cycles",
        description="dependency graph must be acyclic", scope=[b.id],
    ))
    ks.diagnostics = {"files_discovered": 1, "parse_failures": 0}
    return ks


def test_schema_version_is_persisted():
    assert _surface().to_dict()["schema_version"] == SCHEMA_VERSION


def test_duplicate_entity_with_different_content_is_rejected():
    ks = KnowledgeSurface()
    e = _entity("a")
    ks.add_entity(e)
    with pytest.raises(SchemaError, match="duplicate entity"):
        ks.add_entity(e.model_copy(update={"name": "renamed"}))


def test_duplicate_entity_with_same_content_is_idempotent():
    ks = KnowledgeSurface()
    e = _entity("a")
    assert ks.add_entity(e) == e
    assert ks.add_entity(e.model_copy()) == e
    assert len(ks.entities()) == 1


def test_relationship_requires_existing_endpoints():
    ks = KnowledgeSurface()
    a = ks.add_entity(_entity("a"))
    with pytest.raises(KeyError):
        ks.add_relationship(Relationship(
            id="r", source=a.id, target="missing", kind=RelationKind.IMPORTS,
        ))
    with pytest.raises(KeyError):
        ks.add_relationship(Relationship(
            id="r2", source="missing", target=a.id, kind=RelationKind.IMPORTS,
        ))


def test_serialization_is_sorted_and_stable():
    ks = KnowledgeSurface()
    for name in ("z", "a", "m"):
        ks.add_entity(_entity(name))
    first = json.dumps(ks.to_dict(), sort_keys=True)
    second = json.dumps(ks.to_dict(), sort_keys=True)
    assert first == second
    ids = [e["id"] for e in ks.to_dict()["entities"]]
    assert ids == sorted(ids)


def test_roundtrip_preserves_document():
    ks = _surface()
    document = ks.to_dict()
    restored = KnowledgeSurface.from_dict(document)
    assert restored.to_dict() == document
    assert restored.stats() == ks.stats()
    assert restored.diagnostics == ks.diagnostics


def test_newer_schema_version_is_rejected():
    data = _surface().to_dict()
    data["schema_version"] = SCHEMA_VERSION + 1
    with pytest.raises(SchemaError, match="unsupported schema_version"):
        KnowledgeSurface.from_dict(data)


def test_non_integer_schema_version_is_rejected():
    data = _surface().to_dict()
    data["schema_version"] = "1"
    with pytest.raises(SchemaError, match="invalid schema_version"):
        KnowledgeSurface.from_dict(data)


def test_invalid_entity_payload_is_rejected():
    data = _surface().to_dict()
    data["entities"].append({"id": "x", "kind": "not-a-kind", "name": "x"})
    with pytest.raises(SchemaError):
        KnowledgeSurface.from_dict(data)


def test_unknown_invariant_scope_is_a_validation_error():
    ks = KnowledgeSurface()
    ks.add_invariant(Invariant(
        id="i", name="i", description="d", scope=["missing"],
    ))
    result = ks.validate()
    assert result["errors"]
    with pytest.raises(SchemaError):
        KnowledgeSurface.from_dict(ks.to_dict())


def test_cycle_is_a_warning_not_a_crash():
    ks = KnowledgeSurface()
    a = ks.add_entity(_entity("a"))
    b = ks.add_entity(_entity("b"))
    ks.add_relationship(Relationship(
        id="ab", source=a.id, target=b.id, kind=RelationKind.IMPORTS,
    ))
    ks.add_relationship(Relationship(
        id="ba", source=b.id, target=a.id, kind=RelationKind.IMPORTS,
    ))
    result = ks.validate()
    assert not result["errors"]
    assert any("cycle" in w for w in result["warnings"])


def test_invariant_edges_are_not_code_dependencies():
    ks = _surface()
    a = next(e for e in ks.entities() if e.name == "a")
    b = next(e for e in ks.entities() if e.name == "b")
    assert ks.dependencies(a.id) == {b.id}
    assert "constrains" not in {
        r.kind.value for r in ks.relationships(RelationKind.IMPORTS)
    }
    assert ks.dependents(b.id) == {a.id}


def test_unknowns_are_reported_not_hidden():
    ks = KnowledgeSurface()
    ks.add_entity(_entity("mystery").model_copy(
        update={"confidence": Confidence.UNKNOWN}
    ))
    assert any("mystery" in u for u in ks.unknowns())
