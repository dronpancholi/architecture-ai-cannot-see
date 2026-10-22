"""Semantic verification engine.

The engine builds before/after Knowledge Surfaces from an in-memory change,
evaluates every rule against both, and reports only *regressions* — failures
introduced by the change. Pre-existing failures are recorded separately and
never block. Behavioral rules execute in an isolated subprocess.
"""

from __future__ import annotations

import subprocess
import sys
import tempfile
import textwrap
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..extractors.python_ast import PythonASTExtractor
from ..representation.entities import Confidence
from ..representation.knowledge_surface import KnowledgeSurface
from .change import ChangeSet
from .rules import Allowlist, BehavioralRule, Rule, RuleContext, RuleResult


@dataclass
class Finding:
    rule_id: str
    path: str
    line: int
    message: str
    evidence: str
    suggestion: str
    severity: str = "error"
    introduced: bool = True
    confidence: str = "known"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id, "path": self.path, "line": self.line,
            "message": self.message, "evidence": self.evidence,
            "suggestion": self.suggestion, "severity": self.severity,
            "introduced": self.introduced, "confidence": self.confidence,
        }


@dataclass
class VerificationReport:
    approved: bool
    findings: list[Finding] = field(default_factory=list)
    preexisting: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    rules_evaluated: int = 0
    duration_ms: float = 0.0

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.introduced and f.severity == "error"]

    def summary(self) -> str:
        if self.approved:
            return f"APPROVED ({self.rules_evaluated} rules, {len(self.preexisting)} pre-existing)"
        return f"BLOCKED: {len(self.blocking)} introduced violation(s)"

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "summary": self.summary(),
            "findings": [f.to_dict() for f in self.findings],
            "preexisting": [f.to_dict() for f in self.preexisting],
            "suppressed": [f.to_dict() for f in self.suppressed],
            "rules_evaluated": self.rules_evaluated,
            "duration_ms": round(self.duration_ms, 2),
        }


def _build_from_tree(tree: dict[str, str], name: str) -> KnowledgeSurface:
    with tempfile.TemporaryDirectory(prefix="ks-surface-") as td:
        root = Path(td)
        for path, content in tree.items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        return PythonASTExtractor(root).build(name=name)


def _run_behavioral(rule: BehavioralRule, tree: dict[str, str], timeout: float = 5.0) -> RuleResult:
    """Execute the rule snippet in a subprocess against the post-change tree."""
    with tempfile.TemporaryDirectory(prefix="ks-behavior-") as td:
        root = Path(td)
        for path, content in tree.items():
            p = root / path
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content)
        harness = root / "_ks_behavior_check.py"
        harness.write_text(textwrap.dedent(rule.snippet) + "\n\nif __name__ == '__main__':\n    check()\n")
        try:
            proc = subprocess.run(
                [sys.executable, str(harness)], cwd=root,
                capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return RuleResult(
                rule_id=rule.id, passed=False, confidence=Confidence.UNKNOWN,
                message=f"behavioral check timed out after {timeout}s",
                evidence="timeout", suggestion="Inspect the check for non-termination.",
            )
        if proc.returncode == 0:
            return RuleResult(rule_id=rule.id, passed=True, message="behavioral check passed")
        detail = (proc.stdout + "\n" + proc.stderr).strip().splitlines()
        msg = detail[-1] if detail else "behavioral check failed"
        return RuleResult(
            rule_id=rule.id, passed=False, message=f"behavioral violation: {msg}",
            evidence="\n".join(detail[-20:]),
            suggestion="Restore the behavior the invariant requires.",
        )


class SemanticVerifier:
    def __init__(self, rules: list[Rule], allowlist: Allowlist | None = None,
                 block_on_preexisting: bool = False):
        self.rules = rules
        self.allowlist = allowlist or Allowlist()
        self.block_on_preexisting = block_on_preexisting

    def verify(self, root: Path, changes: ChangeSet) -> VerificationReport:
        start = time.perf_counter()
        before_tree = _read_tree(root)
        after_tree = changes.after_tree(root)
        before = _build_from_tree(before_tree, "before")
        after = _build_from_tree(after_tree, "after")
        ctx = RuleContext(
            before=before, after=after, changes=changes,
            before_tree=before_tree, after_tree=after_tree,
        )

        findings: list[Finding] = []
        preexisting: list[Finding] = []
        suppressed: list[Finding] = []

        for rule in self.rules:
            if isinstance(rule, BehavioralRule):
                res_after = _run_behavioral(rule, after_tree)
                res_before = _run_behavioral(rule, before_tree)
            else:
                res_after = rule.evaluate(ctx)
                res_before = rule.evaluate(RuleContext(
                    before=before, after=before, changes=ChangeSet(),
                    before_tree=before_tree, after_tree=before_tree,
                ))
            if res_after.passed:
                continue
            introduced = res_before.passed
            f = Finding(
                rule_id=res_after.rule_id,
                path=res_after.path,
                line=res_after.line,
                message=res_after.message,
                evidence=res_after.evidence,
                suggestion=res_after.suggestion,
                severity=rule.severity,
                introduced=introduced,
                confidence=res_after.confidence.value,
            )
            if self.allowlist.allows(rule.id, res_after.path):
                suppressed.append(f)
            elif introduced:
                findings.append(f)
            else:
                f.introduced = False
                preexisting.append(f)

        approved = not findings
        if self.block_on_preexisting and preexisting:
            approved = False
        return VerificationReport(
            approved=approved, findings=findings, preexisting=preexisting,
            suppressed=suppressed, rules_evaluated=len(self.rules),
            duration_ms=(time.perf_counter() - start) * 1000,
        )


def _read_tree(root: Path) -> dict[str, str]:
    tree: dict[str, str] = {}
    for p in root.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree[str(p.relative_to(root))] = p.read_text()
        except OSError:
            continue
    return tree
