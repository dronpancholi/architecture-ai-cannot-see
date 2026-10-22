"""Semantic Drift detection.

Semantic drift is the gradual accumulation of architectural incoherence in
AI-assisted codebases, resulting from locally correct decisions made without
awareness of the architectural model they contradict.

Detection compares two snapshots. Matching is explainable and conservative:
entities are keyed by kind + name + file, ambiguous matches are skipped, and
every finding carries evidence and confidence. Classes this implementation
cannot decide (for example a semantic rename) are left to human review.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..representation.entities import Confidence, Entity, EntityKind, RelationKind
from ..representation.knowledge_surface import KnowledgeSurface

_RANK = {Confidence.KNOWN: 2, Confidence.INFERRED: 1, Confidence.UNKNOWN: 0}


@dataclass
class DriftFinding:
    kind: str
    severity: str
    message: str
    entities: list[str] = field(default_factory=list)
    confidence: str = "inferred"
    evidence: str = ""
    suggestion: str = ""

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "severity": self.severity,
            "message": self.message,
            "entities": list(self.entities),
            "confidence": self.confidence,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
        }


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

    def to_dict(self) -> dict:
        return {
            "summary": self.summary(),
            "has_drift": self.has_drift,
            "findings": [f.to_dict() for f in self.findings],
        }


def _key(e: Entity) -> tuple:
    return (e.kind, e.name, e.location.file if e.location else "")


def _group(entities: list[Entity], key_fn) -> dict:
    out: dict = {}
    for e in entities:
        out.setdefault(key_fn(e), []).append(e)
    return out


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
        self._detect_relationship_change(report)
        self._detect_provenance_loss(report)
        self._detect_partial_extraction(report)
        report.findings.sort(key=lambda f: (f.kind, f.message, f.entities))
        return report

    # --- concepts ---------------------------------------------------------

    def _detect_duplicate_concepts(self, report: DriftReport) -> None:
        before_groups = _group(
            self.before.entities(),
            lambda e: (e.kind, e.name.lower()),
        )
        after_groups = _group(
            self.after.entities(),
            lambda e: (e.kind, e.name.lower()),
        )
        for key, ents in sorted(after_groups.items()):
            files = {e.location.file if e.location else "" for e in ents}
            before_count = len(before_groups.get(key, []))
            if len(ents) > 1 and len(files) > 1:
                scope = "pre-existing" if before_count >= len(ents) else "new"
                report.findings.append(DriftFinding(
                    kind="duplicate-concept",
                    severity="warning",
                    message=(
                        f"{key[0].value} '{key[1]}' is implemented in "
                        f"{len(files)} files ({scope} duplication)"
                    ),
                    entities=[e.id for e in ents],
                    confidence="inferred",
                    evidence=", ".join(sorted(files)),
                    suggestion="Decide which implementation is canonical, or declare them distinct.",
                ))

    def _detect_invariant_loss(self, report: DriftReport) -> None:
        before_by_id = {i.id: i for i in self.before.invariants()}
        after_ids = {i.id for i in self.after.invariants()}
        for inv_id, inv in sorted(before_by_id.items()):
            if inv_id not in after_ids:
                report.findings.append(DriftFinding(
                    kind="invariant-loss",
                    severity=inv.severity if inv.severity in ("error", "warning", "info") else "error",
                    message=f"invariant '{inv.name}' present before, missing after",
                    entities=list(inv.scope),
                    confidence=inv.confidence.value,
                    evidence=inv.description,
                    suggestion="Restore the invariant or record why it no longer applies.",
                ))

    def _detect_confidence_regression(self, report: DriftReport) -> None:
        before_groups = _group(self.before.entities(), _key)
        after_groups = _group(self.after.entities(), _key)
        for key, ents in sorted(after_groups.items()):
            prev = before_groups.get(key, [])
            if len(prev) != 1 or len(ents) != 1:
                # Ambiguous or new: do not guess which entity regressed.
                continue
            old, new = prev[0], ents[0]
            if _RANK[new.confidence] < _RANK[old.confidence]:
                report.findings.append(DriftFinding(
                    kind="confidence-regression",
                    severity="warning",
                    message=(
                        f"'{new.name}' confidence regressed "
                        f"{old.confidence.value}->{new.confidence.value}"
                    ),
                    entities=[old.id, new.id],
                    confidence=new.confidence.value,
                    evidence=str(new.location) if new.location else "",
                    suggestion="Re-establish the fact or mark the uncertainty explicitly.",
                ))

    def _detect_naming_divergence(self, report: DriftReport) -> None:
        def norm(e: Entity) -> str:
            return e.name.lower().replace("_", "")

        after_groups = _group(self.after.entities(EntityKind.CLASS), norm)
        before_groups = _group(self.before.entities(EntityKind.CLASS), norm)
        for key, ents in sorted(after_groups.items()):
            names = {e.name for e in ents}
            if len(names) < 2:
                continue
            # Only report variants introduced by this change.
            if len(before_groups.get(key, [])) >= len(ents):
                continue
            report.findings.append(DriftFinding(
                kind="naming-divergence",
                severity="info",
                message=f"classes {sorted(names)} may name the same concept differently",
                entities=[e.id for e in ents],
                confidence="inferred",
                evidence="normalized names match after removing case and underscores",
                suggestion="Confirm whether these classes represent one concept.",
            ))

    # --- relationships and provenance ------------------------------------

    def _detect_relationship_change(self, report: DriftReport) -> None:
        def edges(ks: KnowledgeSurface) -> set[tuple[str, str, str]]:
            names = {e.id: e.name for e in ks.entities()}
            return {
                (r.kind.value, names.get(r.source, r.source), names.get(r.target, r.target))
                for r in ks.relationships(RelationKind.IMPORTS)
            }

        before, after = edges(self.before), edges(self.after)
        added = sorted(after - before)
        removed = sorted(before - after)
        if added or removed:
            report.findings.append(DriftFinding(
                kind="relationship-change",
                severity="info",
                message=f"import edges: {len(added)} added, {len(removed)} removed",
                confidence="known",
                evidence=f"added={added[:10]} removed={removed[:10]}",
                suggestion="Review new or removed dependencies for layer violations.",
            ))

    def _detect_provenance_loss(self, report: DriftReport) -> None:
        before_map = {_key(e): e for e in self.before.entities()}
        for e in self.after.entities():
            old = before_map.get(_key(e))
            if old is None:
                continue
            if old.provenance.created_by and not e.provenance.created_by:
                report.findings.append(DriftFinding(
                    kind="provenance-loss",
                    severity="warning",
                    message=f"'{e.name}' lost provenance created_by='{old.provenance.created_by}'",
                    entities=[old.id, e.id],
                    confidence="known",
                    evidence="provenance.created_by is empty after the change",
                    suggestion="Restore the origin of this fact.",
                ))

    def _detect_partial_extraction(self, report: DriftReport) -> None:
        failures = self.after.diagnostics.get("parse_failures", 0)
        if failures:
            report.findings.append(DriftFinding(
                kind="partial-extraction",
                severity="warning",
                message=f"{failures} file(s) could not be parsed; drift comparison is partial",
                confidence="unknown",
                evidence=str(self.after.diagnostics.get("parse_errors", ""))[:500],
                suggestion="Fix parse failures before trusting this comparison.",
            ))
