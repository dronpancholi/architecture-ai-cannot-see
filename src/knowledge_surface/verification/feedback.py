"""Actionable feedback for an AI agent (or human) from a verification report."""

from __future__ import annotations

from .engine import VerificationReport


def feedback_items(report: VerificationReport) -> list[dict]:
    return [
        {
            "rule": f.rule_id,
            "file": f.path,
            "line": f.line,
            "problem": f.message,
            "evidence": f.evidence,
            "fix": f.suggestion,
            "blocking": f.introduced and f.severity == "error",
        }
        for f in report.findings
    ]


def to_markdown(report: VerificationReport) -> str:
    if report.approved:
        return f"## Verification: APPROVED\n\n{report.summary()}\n"
    lines = ["## Verification: BLOCKED\n", report.summary(), ""]
    for f in report.findings:
        lines.append(f"### {f.rule_id} — `{f.path}:{f.line}`")
        lines.append(f"- **Problem:** {f.message}")
        if f.evidence:
            lines.append(f"- **Evidence:** `{f.evidence}`")
        lines.append(f"- **Fix:** {f.suggestion}")
        lines.append("")
    if report.preexisting:
        lines.append(f"_{len(report.preexisting)} pre-existing issue(s) not caused by this change._")
    return "\n".join(lines)
