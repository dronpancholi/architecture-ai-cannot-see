"""Semantic Drift detection.

Semantic drift is the gradual accumulation of architectural incoherence in
AI-assisted codebases, resulting from locally correct decisions made without
awareness of the architectural model they contradict.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..representation.entities import Confidence, Entity, EntityKind
from ..representation.knowledge_surface import KnowledgeSurface


@dataclass
class DriftFinding:
    kind: str
    severity: str
    message: str
    entities: list[str] = field(default_factory=list)


@dataclass
class DriftReport:
    findings: list[DriftFinding] = field(default_factory=list)

    @property
    def has_drift(self) -> bool:
        return len(self.findings) > 0

    def summary(self) -> str:
        if not self.findings:
            return "No semantic drift detected."
        return f"{len(self.findings)} drift finding(s)."


class SemanticDriftDetector:
    def __init__(self, before: KnowledgeSurface, after: KnowledgeSurface):
        self.before = before
        self.after = after

    def detect(self) -> DriftReport:
        report = DriftReport()
        self._detect_duplicate_concepts(report)
        self._detect_invariant_loss(report)
        self._detect_confidence_regression(report)
        self._detect_naming_divergence(report)
        return report

    def _detect_duplicate_concepts(self, report: DriftReport) -> None:
        # Same conceptual name appearing as two distinct entities in 'after'
        # that were one before (or two different implementations of one concept).
        by_name: dict[str, list[Entity]] = {}
        for e in self.after.entities():
            by_name.setdefault(e.name.lower(), []).append(e)
        for name, ents in by_name.items():
            if len(ents) > 1 and len({e.location.file if e.location else "" for e in ents}) > 1:
                report.findings.append(DriftFinding(
                    kind="duplicate-concept",
                    severity="warning",
                    message=f"concept '{name}' implemented in {len(ents)} distinct entities/files",
                    entities=[e.id for e in ents],
                ))

    def _detect_invariant_loss(self, report: DriftReport) -> None:
        before_ids = {i.name for i in self.before.invariants()}
        after_ids = {i.name for i in self.after.invariants()}
        lost = before_ids - after_ids
        for name in lost:
            report.findings.append(DriftFinding(
                kind="invariant-loss",
                severity="error",
                message=f"invariant '{name}' present before, missing after",
                entities=[],
            ))

    def _detect_confidence_regression(self, report: DriftReport) -> None:
        # An entity known before but unknown/inferred after (with same name) = regression
        before_map = {e.name: e for e in self.before.entities()}
        for e in self.after.entities():
            prev = before_map.get(e.name)
            if prev is not None:
                rank = {Confidence.KNOWN: 2, Confidence.INFERRED: 1, Confidence.UNKNOWN: 0}
                if rank[e.confidence] < rank[prev.confidence]:
                    report.findings.append(DriftFinding(
                        kind="confidence-regression",
                        severity="warning",
                        message=f"'{e.name}' confidence regressed {prev.confidence.value}->{e.confidence.value}",
                        entities=[prev.id, e.id],
                    ))

    def _detect_naming_divergence(self, report: DriftReport) -> None:
        # Heuristic: two entities whose names differ only by casing/underscore
        # but live in different modules -> possible same concept, divergent naming
        names = [e.name for e in self.after.entities(EntityKind.CLASS)]
        seen: set[str] = set()
        for n in names:
            key = n.lower().replace("_", "")
            if key in seen:
                # find the other
                others = [e for e in self.after.entities(EntityKind.CLASS) if e.name.lower().replace("_", "") == key and e.name != n]
                if not others:
                    seen.add(key)
                    continue
                report.findings.append(DriftFinding(
                    kind="naming-divergence",
                    severity="info",
                    message=f"classes '{n}' and {[o.name for o in others]} may name the same concept differently",
                    entities=[e.id for e in self.after.entities(EntityKind.CLASS) if e.name.lower().replace("_", "") == key],
                ))
            seen.add(key)
