"""Semantic verification engine.

The engine materializes the complete before/after Python trees, evaluates every
rule against both, and classifies each result as introduced, pre-existing,
improved, or unknown. An unknown result is never treated as a pass.

The default ``unknown_policy`` is ``block``: a change cannot be approved while
any rule result (or any changed file) is indeterminate. CI operators can choose
``warn`` or ``ignore`` for non-critical rule sets; the report records what was
chosen and which results were indeterminate.
"""

from __future__ import annotations

import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path

from ..extractors.python_ast import PythonASTExtractor
from ..paths import read_tree, safe_write
from ..representation.knowledge_surface import KnowledgeSurface
from .change import ChangeSet, parse_python
from .rules import Allowlist, BehavioralRule, Outcome, Rule, RuleContext, RuleResult
from .sandbox import run_behavioral

_POLICIES = {"block", "warn", "ignore"}


@dataclass
class Finding:
    rule_id: str
    path: str
    line: int
    message: str
    evidence: str
    suggestion: str
    severity: str = "error"
    status: str = "introduced"   # introduced | preexisting | unknown
    before: str = ""
    after: str = ""
    confidence: str = "known"
    suppressed: bool = False
    suppression_reason: str = ""

    @property
    def introduced(self) -> bool:
        return self.status == "introduced"

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "path": self.path,
            "line": self.line,
            "message": self.message,
            "evidence": self.evidence,
            "suggestion": self.suggestion,
            "severity": self.severity,
            "status": self.status,
            "introduced": self.introduced,
            "before": self.before,
            "after": self.after,
            "confidence": self.confidence,
            "suppressed": self.suppressed,
            "suppression_reason": self.suppression_reason,
        }


@dataclass
class VerificationReport:
    approved: bool
    findings: list[Finding] = field(default_factory=list)
    preexisting: list[Finding] = field(default_factory=list)
    unknown: list[Finding] = field(default_factory=list)
    improvements: list[Finding] = field(default_factory=list)
    suppressed: list[Finding] = field(default_factory=list)
    parse_errors: list[dict] = field(default_factory=list)
    rule_results: list[dict] = field(default_factory=list)
    rules_evaluated: int = 0
    duration_ms: float = 0.0
    complete: bool = True
    unknown_policy: str = "block"

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.severity == "error"]

    @property
    def indeterminate(self) -> bool:
        return bool(self.unknown) or not self.complete

    def summary(self) -> str:
        if self.approved:
            suffix = f", {len(self.preexisting)} pre-existing" if self.preexisting else ""
            return f"APPROVED ({self.rules_evaluated} rules{suffix})"
        if self.indeterminate and self.unknown_policy == "block":
            return (
                f"INDETERMINATE: {len(self.unknown)} unknown result(s), "
                f"{len(self.parse_errors)} parse error(s), policy=block"
            )
        return f"BLOCKED: {len(self.blocking)} introduced violation(s)"

    def to_dict(self) -> dict:
        return {
            "approved": self.approved,
            "summary": self.summary(),
            "complete": self.complete,
            "unknown_policy": self.unknown_policy,
            "findings": [f.to_dict() for f in self.findings],
            "preexisting": [f.to_dict() for f in self.preexisting],
            "unknown": [f.to_dict() for f in self.unknown],
            "improvements": [f.to_dict() for f in self.improvements],
            "suppressed": [f.to_dict() for f in self.suppressed],
            "parse_errors": list(self.parse_errors),
            "rule_results": list(self.rule_results),
            "rules_evaluated": self.rules_evaluated,
            "duration_ms": round(self.duration_ms, 2),
        }

    def to_json(self) -> str:
        import json

        return json.dumps(self.to_dict(), indent=2, sort_keys=True)


def _build_from_tree(tree: dict[str, str], name: str) -> KnowledgeSurface:
    with tempfile.TemporaryDirectory(prefix="ks-surface-") as td:
        root = Path(td)
        for path, content in tree.items():
            safe_write(root, path, content)
        return PythonASTExtractor(root).build(name=name)


def _parse_errors(tree: dict[str, str]) -> dict[str, str]:
    errors: dict[str, str] = {}
    for path, source in sorted(tree.items()):
        _, error = parse_python(source, path)
        if error:
            errors[path] = error
    return errors


def _finding(rule: Rule, result: RuleResult, status: str, before: str) -> Finding:
    return Finding(
        rule_id=result.rule_id or rule.id,
        path=result.path,
        line=result.line,
        message=result.message,
        evidence=result.evidence,
        suggestion=result.suggestion,
        severity=rule.severity,
        status=status,
        before=before,
        after=result.outcome.value,
        confidence=result.confidence.value,
    )


def _sort_key(f: Finding) -> tuple:
    return (f.path, f.line, f.rule_id, f.status)


class SemanticVerifier:
    def __init__(
        self,
        rules: list[Rule],
        allowlist: Allowlist | None = None,
        block_on_preexisting: bool = False,
        unknown_policy: str = "block",
        allow_untrusted_behavioral: bool = False,
        behavioral_timeout: float = 5.0,
    ):
        if unknown_policy not in _POLICIES:
            raise ValueError(f"unknown_policy must be one of {sorted(_POLICIES)}")
        self.rules = rules
        self.allowlist = allowlist or Allowlist()
        self.block_on_preexisting = block_on_preexisting
        self.unknown_policy = unknown_policy
        self.allow_untrusted_behavioral = allow_untrusted_behavioral
        self.behavioral_timeout = behavioral_timeout

    # --- public API -------------------------------------------------------

    def verify(self, root: Path, changes: ChangeSet) -> VerificationReport:
        start = time.perf_counter()
        validated = changes.validate(root)
        before_tree = read_tree(root)
        after_tree = validated.after_tree(root)
        before_errors = _parse_errors(before_tree)
        after_errors = _parse_errors(after_tree)

        before = _build_from_tree(before_tree, "before")
        after = _build_from_tree(after_tree, "after")
        changed = set(validated.touched_paths())

        ctx = RuleContext(
            before=before, after=after, changes=validated,
            before_tree=before_tree, after_tree=after_tree,
            before_errors=before_errors, after_errors=after_errors,
        )
        baseline_ctx = RuleContext(
            before=before, after=before, changes=ChangeSet(),
            before_tree=before_tree, after_tree=before_tree,
            before_errors=before_errors, after_errors=before_errors,
        )

        findings: list[Finding] = []
        preexisting: list[Finding] = []
        unknown: list[Finding] = []
        improvements: list[Finding] = []
        suppressed: list[Finding] = []
        rule_results: list[dict] = []
        complete = validated.complete and not after_errors

        for rule in self.rules:
            before_result, after_result = self._evaluate(rule, ctx, baseline_ctx,
                                                          before_tree, after_tree)
            rule_results.append({
                "rule_id": rule.id,
                "before": before_result.outcome.value,
                "after": after_result.outcome.value,
                "message": after_result.message if after_result.outcome is not Outcome.PASS else "",
                "path": after_result.path,
                "line": after_result.line,
            })
            self._classify(
                rule, before_result, after_result,
                findings, preexisting, unknown, improvements, suppressed,
            )

        # Parse errors are first-class diagnostics, never silent.
        for path, error in sorted(after_errors.items()):
            status = "unknown" if path in changed else "preexisting"
            f = Finding(
                rule_id="parse-error", path=path, line=0,
                message=f"cannot parse candidate file: {error}",
                evidence=error,
                suggestion="Fix the syntax error or remove the file from the change.",
                severity="error", status=status,
                before=before_errors.get(path, ""), after=error,
                confidence="unknown",
            )
            self._route(f, findings, preexisting, unknown, suppressed)
            complete = False

        if not validated.complete:
            f = Finding(
                rule_id="unsupported-change", path="", line=0,
                message="change contains a binary or otherwise unsupported patch",
                evidence="; ".join(validated.warnings),
                suggestion="Verify binary changes outside the semantic verifier.",
                severity="error", status="unknown", confidence="unknown",
            )
            self._route(f, findings, preexisting, unknown, suppressed)
            complete = False

        findings.sort(key=_sort_key)
        preexisting.sort(key=_sort_key)
        unknown.sort(key=_sort_key)
        improvements.sort(key=_sort_key)
        suppressed.sort(key=_sort_key)

        blocking = bool(findings)
        indeterminate = bool(unknown) or not complete
        approved = not blocking and not (
            self.unknown_policy == "block" and indeterminate
        )
        if self.block_on_preexisting and preexisting:
            approved = False

        return VerificationReport(
            approved=approved,
            findings=findings,
            preexisting=preexisting,
            unknown=unknown,
            improvements=improvements,
            suppressed=suppressed,
            parse_errors=[
                {"path": p, "error": e, "introduced": p in changed}
                for p, e in sorted(after_errors.items())
            ],
            rule_results=rule_results,
            rules_evaluated=len(self.rules),
            duration_ms=(time.perf_counter() - start) * 1000,
            complete=complete,
            unknown_policy=self.unknown_policy,
        )

    # --- internals --------------------------------------------------------

    def _evaluate(self, rule: Rule, ctx: RuleContext, baseline_ctx: RuleContext,
                  before_tree: dict[str, str],
                  after_tree: dict[str, str]) -> tuple[RuleResult, RuleResult]:
        if isinstance(rule, BehavioralRule):
            before = run_behavioral(
                rule.snippet, before_tree, trusted=rule.trusted,
                allow_untrusted=self.allow_untrusted_behavioral,
                timeout=self.behavioral_timeout,
            )
            after = run_behavioral(
                rule.snippet, after_tree, trusted=rule.trusted,
                allow_untrusted=self.allow_untrusted_behavioral,
                timeout=self.behavioral_timeout,
            )
            return (
                RuleResult(rule.id, before.outcome, before.message,
                           evidence=before.evidence),
                RuleResult(rule.id, after.outcome, after.message,
                           evidence=after.evidence),
            )
        before_result = self._safe_evaluate(rule, baseline_ctx)
        after_result = self._safe_evaluate(rule, ctx)
        return before_result, after_result

    @staticmethod
    def _safe_evaluate(rule: Rule, ctx: RuleContext) -> RuleResult:
        try:
            result = rule.evaluate(ctx)
        except Exception as exc:  # a rule bug must not become a pass
            return RuleResult.unknown(
                rule.id,
                f"rule raised {type(exc).__name__}: {exc}",
                evidence=f"{type(exc).__name__}: {exc}",
                suggestion="Fix the rule; the result is indeterminate.",
            )
        return result

    def _classify(
        self,
        rule: Rule,
        before: RuleResult,
        after: RuleResult,
        findings: list[Finding],
        preexisting: list[Finding],
        unknown: list[Finding],
        improvements: list[Finding],
        suppressed: list[Finding],
    ) -> None:
        b = before.outcome
        a = after.outcome
        if a is Outcome.PASS:
            if b is not Outcome.PASS:
                f = _finding(rule, after, "improvement", b.value)
                improvements.append(f)
            return
        if a is Outcome.UNKNOWN:
            self._route(_finding(rule, after, "unknown", b.value),
                        findings, preexisting, unknown, suppressed)
            return
        # a is FAIL. A target that was absent before and is still absent is
        # pre-existing; adding a target that violates, or removing one that
        # used to exist, is introduced.
        if after.missing_target:
            status = "preexisting" if before.missing_target and b is Outcome.FAIL else "introduced"
        elif b is Outcome.PASS or before.missing_target:
            status = "introduced"
        elif b is Outcome.FAIL:
            status = "preexisting"
        else:
            status = "unknown"
        self._route(_finding(rule, after, status, b.value),
                    findings, preexisting, unknown, suppressed)

    def _route(
        self,
        finding: Finding,
        findings: list[Finding],
        preexisting: list[Finding],
        unknown: list[Finding],
        suppressed: list[Finding],
    ) -> None:
        reason = self.allowlist.reason(finding.rule_id, finding.path)
        if reason is not None:
            finding.suppressed = True
            finding.suppression_reason = reason
            suppressed.append(finding)
        elif finding.status == "introduced":
            findings.append(finding)
        elif finding.status == "preexisting":
            preexisting.append(finding)
        else:
            unknown.append(finding)
