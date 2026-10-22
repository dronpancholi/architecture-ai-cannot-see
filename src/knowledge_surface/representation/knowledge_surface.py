"""The Knowledge Surface: the structured, queryable representation of both
architectures of a software system (the written and the unwritten).

This is the Representation Layer's output artifact.

Serialization is deterministic: entities, relationships, and invariants are
emitted in ID order. A schema version is persisted so incompatible documents
fail explicitly instead of being silently misread.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from .entities import Confidence, Entity, EntityKind, Invariant, RelationKind, Relationship

SCHEMA_VERSION = 1


class SchemaError(ValueError, KeyError):
    """A persisted Knowledge Surface is invalid or uses an unsupported schema.

    Also a ``KeyError`` so callers that previously caught missing endpoints
    keep working.
    """


@dataclass
class KnowledgeSurface:
    name: str = "knowledge-surface"
    _entities: dict[str, Entity] = field(default_factory=dict)
    _relationships: dict[str, Relationship] = field(default_factory=dict)
    _invariants: dict[str, Invariant] = field(default_factory=dict)
    _graph: nx.DiGraph = field(default_factory=nx.DiGraph)
    diagnostics: dict = field(default_factory=dict)

    # --- mutation ---------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        if not entity.id:
            raise SchemaError("entity id must not be empty")
        existing = self._entities.get(entity.id)
        if existing is not None:
            if existing == entity:
                return existing
            raise SchemaError(f"duplicate entity id with different content: {entity.id}")
        self._entities[entity.id] = entity
        self._graph.add_node(entity.id, kind=entity.kind.value, name=entity.name)
        return entity

    def add_relationship(self, rel: Relationship) -> Relationship:
        if not rel.id:
            raise SchemaError("relationship id must not be empty")
        if rel.source not in self._entities:
            raise SchemaError(f"unknown source entity: {rel.source}")
        if rel.target not in self._entities:
            raise SchemaError(f"unknown target entity: {rel.target}")
        existing = self._relationships.get(rel.id)
        if existing is not None:
            if existing == rel:
                return existing
            raise SchemaError(f"duplicate relationship id with different content: {rel.id}")
        self._relationships[rel.id] = rel
        self._graph.add_edge(rel.source, rel.target, kind=rel.kind.value, id=rel.id)
        return rel

    def add_invariant(self, inv: Invariant) -> Invariant:
        if not inv.id:
            raise SchemaError("invariant id must not be empty")
        existing = self._invariants.get(inv.id)
        if existing is not None:
            if existing == inv:
                return existing
            raise SchemaError(f"duplicate invariant id with different content: {inv.id}")
        self._invariants[inv.id] = inv
        for eid in inv.scope:
            if eid in self._entities:
                self._graph.add_edge(inv.id, eid, kind=RelationKind.CONSTRAINS.value, id=inv.id)
        return inv

    # --- access -----------------------------------------------------------

    def entity(self, eid: str) -> Entity | None:
        return self._entities.get(eid)

    def has_relationship(self, rid: str) -> bool:
        return rid in self._relationships

    def entities(self, kind: EntityKind | None = None) -> list[Entity]:
        out = list(self._entities.values())
        if kind is not None:
            out = [e for e in out if e.kind == kind]
        return out

    def relationships(self, kind: RelationKind | None = None) -> list[Relationship]:
        out = list(self._relationships.values())
        if kind is not None:
            out = [r for r in out if r.kind == kind]
        return out

    def invariants(self) -> list[Invariant]:
        return list(self._invariants.values())

    def invariants_for(self, eid: str) -> list[Invariant]:
        return [inv for inv in self._invariants.values() if eid in inv.scope]

    def _code_graph(self) -> nx.DiGraph:
        """A view containing code entities only.

        Invariant nodes and invariant-to-entity edges are representation
        infrastructure, not code dependencies. They must not appear in
        dependency answers.
        """
        return nx.subgraph_view(self._graph, filter_node=lambda n: n in self._entities)

    def dependents(self, eid: str) -> set[str]:
        """Entities that (transitively) depend on eid."""
        if eid not in self._entities:
            return set()
        # reverse reachability
        rg = self._code_graph().reverse(copy=False)
        if eid not in rg:
            return set()
        reachable = nx.descendants(rg, eid)
        return reachable - {eid}

    def dependencies(self, eid: str) -> set[str]:
        if eid not in self._entities:
            return set()
        graph = self._code_graph()
        if eid not in graph:
            return set()
        return nx.descendants(graph, eid)

    def path(self, src: str, dst: str) -> list[str] | None:
        try:
            return nx.shortest_path(self._code_graph(), src, dst)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            return None

    # --- honesty ----------------------------------------------------------

    def confidence_summary(self) -> dict[str, int]:
        counts: dict[str, int] = defaultdict(int)
        for e in self._entities.values():
            counts[e.confidence.value] += 1
        for r in self._relationships.values():
            counts[f"rel:{r.confidence.value}"] += 1
        return dict(counts)

    def unknowns(self) -> list[str]:
        """Surface honest uncertainty: things we do not know."""
        out: list[str] = []
        for e in self._entities.values():
            if e.confidence == Confidence.UNKNOWN:
                out.append(f"entity:{e.name} ({e.kind.value}) is unknown")
        for r in self._relationships.values():
            if r.confidence == Confidence.UNKNOWN:
                out.append(f"relationship {r.source}->{r.target} ({r.kind.value}) is unknown")
        for inv in self._invariants.values():
            if inv.confidence == Confidence.UNKNOWN:
                out.append(f"invariant {inv.name} is unknown")
        return out

    # --- validation -------------------------------------------------------

    def validate(self) -> dict[str, list[str]]:
        """Return ``{"errors": [...], "warnings": [...]}`` without mutating."""
        errors: list[str] = []
        warnings: list[str] = []
        if not self.name:
            errors.append("surface name is empty")
        for key, entity in self._entities.items():
            if entity.id != key:
                errors.append(f"entity key {key!r} does not match id {entity.id!r}")
            if not entity.name:
                errors.append(f"entity {key}: empty name")
        for key, rel in self._relationships.items():
            if rel.id != key:
                errors.append(f"relationship key {key!r} does not match id {rel.id!r}")
            if rel.source not in self._entities:
                errors.append(f"relationship {key}: missing source {rel.source}")
            if rel.target not in self._entities:
                errors.append(f"relationship {key}: missing target {rel.target}")
        for key, inv in self._invariants.items():
            if not inv.name:
                errors.append(f"invariant {key}: empty name")
            for eid in inv.scope:
                if eid not in self._entities:
                    errors.append(f"invariant {key}: unknown scope entity {eid}")
        if self._entities and not nx.is_directed_acyclic_graph(self._code_graph()):
            warnings.append("code dependency graph contains a cycle")
        return {"errors": errors, "warnings": warnings}

    # --- serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "schema_version": SCHEMA_VERSION,
            "name": self.name,
            "entities": [self._entities[k].model_dump(mode="json") for k in sorted(self._entities)],
            "relationships": [
                self._relationships[k].model_dump(mode="json")
                for k in sorted(self._relationships)
            ],
            "invariants": [self._invariants[k].model_dump(mode="json") for k in sorted(self._invariants)],
            "diagnostics": self.diagnostics,
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeSurface:
        if not isinstance(data, dict):
            raise SchemaError("Knowledge Surface document must be a JSON object")
        version = data.get("schema_version", 0)
        if not isinstance(version, int) or isinstance(version, bool):
            raise SchemaError(f"invalid schema_version: {version!r}")
        if version > SCHEMA_VERSION:
            raise SchemaError(
                f"unsupported schema_version {version}; this build supports <= {SCHEMA_VERSION}"
            )
        ks = cls(name=data.get("name", "knowledge-surface"),
                 diagnostics=dict(data.get("diagnostics", {})))
        try:
            for e in data.get("entities", []):
                ks.add_entity(Entity.model_validate(e))
            for r in data.get("relationships", []):
                ks.add_relationship(Relationship.model_validate(r))
            for i in data.get("invariants", []):
                ks.add_invariant(Invariant.model_validate(i))
        except (KeyError, ValueError, TypeError) as exc:
            raise SchemaError(f"invalid Knowledge Surface: {exc}") from exc
        result = ks.validate()
        if result["errors"]:
            raise SchemaError("; ".join(result["errors"]))
        return ks

    def stats(self) -> dict[str, int]:
        return {
            "entities": len(self._entities),
            "relationships": len(self._relationships),
            "invariants": len(self._invariants),
            "nodes": self._graph.number_of_nodes(),
            "edges": self._graph.number_of_edges(),
        }

    def __repr__(self) -> str:
        return f"KnowledgeSurface({self.name!r}, {self.stats()})"
