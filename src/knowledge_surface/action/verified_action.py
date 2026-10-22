"""Action Layer: verified action under the constraint of the Reasoning Layer.

An action is not executed until the Reasoning Layer has evaluated it.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..reasoning.consistency import ConsistencyChecker, ConsistencyVerdict
from ..reasoning.propagation import PropagationAnalyzer, PropagationResult, RiskScorer
from ..representation.entities import Entity, Relationship
from ..representation.knowledge_surface import KnowledgeSurface


@dataclass
class VerifiedAction:
    action: str
    approved: bool
    verdict: ConsistencyVerdict
    propagation: PropagationResult | None = None
    risk: Any = None
    explanation: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "approved": self.approved,
            "verdict": self.verdict.summary(),
            "violations": [v.__dict__ for v in self.verdict.violations],
            "unknowns": self.verdict.unknowns,
            "propagation": {
                "blast_radius": self.propagation.blast_radius if self.propagation else 0,
                "affected_invariants": self.propagation.affected_invariants if self.propagation else [],
            },
            "risk": self.risk.as_dict() if self.risk else None,
            "explanation": self.explanation,
        }


class ChangeEvaluator:
    def __init__(self, ks: KnowledgeSurface):
        self.ks = ks
        self.checker = ConsistencyChecker(ks)
        self.prop = PropagationAnalyzer(ks)
        self.risk = RiskScorer(ks)

    def evaluate_add_entity(self, entity: Entity) -> VerifiedAction:
        verdict = self.checker.check_add_entity(entity)
        propagation = None
        risk = None
        if entity.id in self.ks._graph:  # noqa: SLF001
            propagation = self.prop.analyze(entity.id)
            risk = self.risk.score(entity.id)
        approved = verdict.consistent
        explanation = (
            "Change is architecturally consistent." if approved
            else "Change violates one or more invariants; review required before commit."
        )
        return VerifiedAction("add_entity", approved, verdict, propagation, risk, explanation)

    def evaluate_remove_entity(self, eid: str) -> VerifiedAction:
        verdict = self.checker.check_remove_entity(eid)
        propagation = self.prop.analyze(eid) if self.ks.entity(eid) else None
        risk = self.risk.score(eid) if self.ks.entity(eid) else None
        approved = verdict.consistent
        explanation = (
            "Removal is safe." if approved
            else "Removal is unsafe: invariants or dependents affected."
        )
        return VerifiedAction("remove_entity", approved, verdict, propagation, risk, explanation)

    def evaluate_add_relationship(self, rel: Relationship) -> VerifiedAction:
        verdict = self.checker.check_add_relationship(rel)
        approved = verdict.consistent
        return VerifiedAction("add_relationship", approved, verdict, None, None,
                              "Relationship is consistent." if approved else "Relationship inconsistent.")

    def evaluate_change(self, description: str, touched: list[str]) -> VerifiedAction:
        verdict = self.checker.check_change(description, touched)
        # aggregate propagation over touched
        all_deps: set[str] = set()
        for t in touched:
            if self.ks.entity(t):
                all_deps |= self.ks.dependents(t)
        prop = PropagationResult(origin=",".join(touched), transitive_dependents=all_deps, blast_radius=len(all_deps))
        risk = None
        if touched:
            risk = self.risk.score(touched[0])
        approved = verdict.consistent
        explanation = (
            "Change passes architectural review." if approved
            else "Change requires review: invariant scope intersected."
        )
        return VerifiedAction("change", approved, verdict, prop, risk, explanation)
