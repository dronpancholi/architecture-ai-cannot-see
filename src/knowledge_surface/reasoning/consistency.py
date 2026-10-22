"""Reasoning Layer: evaluate proposed changes against the Knowledge Surface.

The Reasoning Layer does not generate code. It evaluates code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    RelationKind,
    Relationship,
)
from ..representation.knowledge_surface import KnowledgeSurface


@dataclass
class Violation:
    invariant: str
    severity: str
    message: str
    affected: list[str] = field(default_factory=list)


@dataclass
class ConsistencyVerdict:
    consistent: bool
    violations: list[Violation] = field(default_factory=list)
    unknowns: list[str] = field(default_factory=list)
    confidence: Confidence = Confidence.INFERRED

    def summary(self) -> str:
        if self.consistent and not self.violations:
            return "CONSISTENT (no invariant violations detected)"
        return f"INCONSISTENT: {len(self.violations)} violation(s)"


class ConsistencyChecker:
    """Check a proposed change against invariants and capability contracts."""

    def __init__(self, ks: KnowledgeSurface):
        self.ks = ks

    def check_add_entity(self, entity: Entity) -> ConsistencyVerdict:
        violations: list[Violation] = []
        # Capability contract check: if entity requires a capability, target must exist
        # (handled via relationships; here we check duplicate-name invariants)
        for existing in self.ks.entities(entity.kind):
            if existing.name == entity.name:
                violations.append(Violation(
                    invariant="unique-name",
                    severity="error",
                    message=f"entity '{entity.name}' already exists ({existing.id})",
                    affected=[existing.id],
                ))
        unknowns = self.ks.unknowns()
        return ConsistencyVerdict(
            consistent=len(violations) == 0,
            violations=violations,
            unknowns=unknowns,
            confidence=Confidence.INFERRED,
        )

    def check_remove_entity(self, eid: str) -> ConsistencyVerdict:
        violations: list[Violation] = []
        ent = self.ks.entity(eid)
        if ent is None:
            violations.append(Violation(
                invariant="existence", severity="error",
                message=f"entity {eid} does not exist",
            ))
            return ConsistencyVerdict(False, violations)
        # Check invariants that scope this entity
        for inv in self.ks.invariants_for(eid):
            violations.append(Violation(
                invariant=inv.name, severity=inv.severity,
                message=f"removing {ent.name} violates invariant: {inv.description}",
                affected=[eid],
            ))
        # Check dependents
        deps = self.ks.dependents(eid)
        if deps:
            violations.append(Violation(
                invariant="dependent-impact",
                severity="warning",
                message=f"removing {ent.name} affects {len(deps)} dependent(s): {sorted(deps)[:5]}",
                affected=sorted(deps),
            ))
        unknowns = self.ks.unknowns()
        # removal with only warnings is still "consistent" but flagged
        hard = [v for v in violations if v.severity == "error"]
        return ConsistencyVerdict(
            consistent=len(hard) == 0,
            violations=violations,
            unknowns=unknowns,
            confidence=Confidence.INFERRED,
        )

    def check_add_relationship(self, rel: Relationship) -> ConsistencyVerdict:
        violations: list[Violation] = []
        # semantic typing: a REQUIRES edge needs the target capability to exist
        if rel.kind == RelationKind.REQUIRES:
            tgt = self.ks.entity(rel.target)
            if tgt is None or tgt.kind != EntityKind.CAPABILITY:
                violations.append(Violation(
                    invariant="capability-exists", severity="error",
                    message=f"REQUIRES target {rel.target} is not a capability",
                    affected=[rel.target],
                ))
        # duplicate edge check
        for existing in self.ks.relationships(rel.kind):
            if existing.source == rel.source and existing.target == rel.target:
                violations.append(Violation(
                    invariant="unique-edge", severity="warning",
                    message=f"relationship {rel.source}->{rel.target} ({rel.kind.value}) already exists",
                    affected=[existing.id],
                ))
        unknowns = self.ks.unknowns()
        hard = [v for v in violations if v.severity == "error"]
        return ConsistencyVerdict(
            consistent=len(hard) == 0,
            violations=violations,
            unknowns=unknowns,
            confidence=Confidence.INFERRED,
        )

    def check_change(self, description: str, touched: list[str]) -> ConsistencyVerdict:
        """Evaluate a free-form change description against invariants whose
        scope intersects touched entities."""
        violations: list[Violation] = []
        touched_set = set(touched)
        for inv in self.ks.invariants():
            if touched_set & set(inv.scope):
                # We cannot prove safety; surface as a required review.
                violations.append(Violation(
                    invariant=inv.name, severity=inv.severity,
                    message=f"change touches invariant '{inv.name}': {inv.description}",
                    affected=sorted(touched_set & set(inv.scope)),
                ))
        unknowns = self.ks.unknowns()
        hard = [v for v in violations if v.severity == "error"]
        return ConsistencyVerdict(
            consistent=len(hard) == 0,
            violations=violations,
            unknowns=unknowns,
            confidence=Confidence.INFERRED,
        )
