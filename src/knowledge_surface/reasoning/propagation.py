"""Propagation analysis and risk scoring for proposed changes."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from ..representation.entities import Confidence
from ..representation.knowledge_surface import KnowledgeSurface


@dataclass
class PropagationResult:
    origin: str
    direct_dependents: set[str] = field(default_factory=set)
    transitive_dependents: set[str] = field(default_factory=set)
    affected_invariants: list[str] = field(default_factory=list)
    blast_radius: int = 0


class PropagationAnalyzer:
    def __init__(self, ks: KnowledgeSurface):
        self.ks = ks

    def analyze(self, eid: str) -> PropagationResult:
        res = PropagationResult(origin=eid)
        if self.ks.entity(eid) is None:
            return res
        g = self.ks._graph  # noqa: SLF001
        direct_imm = set(g.predecessors(eid)) if eid in g else set()
        res.direct_dependents = direct_imm
        res.transitive_dependents = self.ks.dependents(eid)
        res.blast_radius = len(res.transitive_dependents)
        for inv in self.ks.invariants():
            if eid in inv.scope or (set(inv.scope) & res.transitive_dependents):
                res.affected_invariants.append(inv.name)
        return res


@dataclass
class RiskReport:
    entity: str
    fan_in: int
    fan_out: int
    invariant_count: int
    unknown_neighbor_count: int
    score: float          # 0..1
    level: str            # low | medium | high | critical

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity": self.entity, "fan_in": self.fan_in, "fan_out": self.fan_out,
            "invariant_count": self.invariant_count, "unknown_neighbor_count": self.unknown_neighbor_count,
            "score": round(self.score, 3), "level": self.level,
        }


class RiskScorer:
    def __init__(self, ks: KnowledgeSurface):
        self.ks = ks

    def score(self, eid: str) -> RiskReport:
        ent = self.ks.entity(eid)
        name = ent.name if ent else eid
        g = self.ks._graph  # noqa: SLF001
        fan_in = g.in_degree(eid) if eid in g else 0
        fan_out = g.out_degree(eid) if eid in g else 0
        inv_count = len(self.ks.invariants_for(eid))
        # unknown neighbors
        neighbors = set()
        if eid in g:
            neighbors |= set(g.predecessors(eid)) | set(g.successors(eid))
        unknown_n = 0
        for n in neighbors:
            e = self.ks.entity(n)
            if e is not None and e.confidence == Confidence.UNKNOWN:
                unknown_n += 1
            for r in self.ks.relationships():
                if r.source == eid and r.target == n and r.confidence == Confidence.UNKNOWN:
                    unknown_n += 1
        # weighted score
        raw = (fan_in * 0.15 + fan_out * 0.05 + inv_count * 0.25 + unknown_n * 0.2)
        score = min(1.0, raw)
        if score >= 0.75:
            level = "critical"
        elif score >= 0.5:
            level = "high"
        elif score >= 0.25:
            level = "medium"
        else:
            level = "low"
        return RiskReport(
            entity=name, fan_in=fan_in, fan_out=fan_out,
            invariant_count=inv_count, unknown_neighbor_count=unknown_n,
            score=score, level=level,
        )
