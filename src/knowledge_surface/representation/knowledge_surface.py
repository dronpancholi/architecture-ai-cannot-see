"""The Knowledge Surface: the structured, queryable representation of both
architectures of a software system (the written and the unwritten).

This is the Representation Layer's output artifact.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

import networkx as nx

from .entities import Confidence, Entity, EntityKind, Invariant, RelationKind, Relationship


@dataclass
class KnowledgeSurface:
    name: str = "knowledge-surface"
    _entities: dict[str, Entity] = field(default_factory=dict)
    _relationships: dict[str, Relationship] = field(default_factory=dict)
    _invariants: dict[str, Invariant] = field(default_factory=dict)
    _graph: nx.DiGraph = field(default_factory=nx.DiGraph)

    # --- mutation ---------------------------------------------------------

    def add_entity(self, entity: Entity) -> Entity:
        self._entities[entity.id] = entity
        self._graph.add_node(entity.id, kind=entity.kind.value, name=entity.name)
        return entity

    def add_relationship(self, rel: Relationship) -> Relationship:
        if rel.source not in self._entities:
            raise KeyError(f"unknown source entity: {rel.source}")
        if rel.target not in self._entities:
            raise KeyError(f"unknown target entity: {rel.target}")
        self._relationships[rel.id] = rel
        self._graph.add_edge(rel.source, rel.target, kind=rel.kind.value, id=rel.id)
        return rel

    def add_invariant(self, inv: Invariant) -> Invariant:
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

    def dependents(self, eid: str) -> set[str]:
        """Entities that (transitively) depend on eid."""
        if eid not in self._graph:
            return set()
        # reverse reachability
        rg = self._graph.reverse(copy=False)
        reachable = nx.descendants(rg, eid)
        return reachable - {eid}

    def dependencies(self, eid: str) -> set[str]:
        if eid not in self._graph:
            return set()
        return nx.descendants(self._graph, eid)

    def path(self, src: str, dst: str) -> list[str] | None:
        try:
            return nx.shortest_path(self._graph, src, dst)
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

    # --- serialization ----------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "entities": [e.model_dump(mode="json") for e in self._entities.values()],
            "relationships": [r.model_dump(mode="json") for r in self._relationships.values()],
            "invariants": [i.model_dump(mode="json") for i in self._invariants.values()],
        }

    @classmethod
    def from_dict(cls, data: dict) -> KnowledgeSurface:
        ks = cls(name=data.get("name", "knowledge-surface"))
        for e in data.get("entities", []):
            ks.add_entity(Entity.model_validate(e))
        for r in data.get("relationships", []):
            ks.add_relationship(Relationship.model_validate(r))
        for i in data.get("invariants", []):
            ks.add_invariant(Invariant.model_validate(i))
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
