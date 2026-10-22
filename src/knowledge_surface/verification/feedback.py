"""Actionable feedback for an AI agent (or human) from a verification report."""

from __future__ import annotations

from .engine import Finding, VerificationReport


def _item(f: Finding, blocking: bool) -> dict:
    return {
        "rule": f.rule_id,
        "key": f.key,
        "file": f.path,
        "line": f.line,
        "problem": f.message,
        "evidence": f.evidence,
        "fix": f.suggestion,
        "status": f.status,
        "before": f.before,
        "after": f.after,
        "blocking": blocking,
        "suppressed": f.suppressed,
        "suppression_reason": f.suppression_reason,
    }


def feedback_items(report: VerificationReport) -> list[dict]:
    items = [
        _item(f, True)
        for f in report.findings
        if f.severity == "error"
    ]
    items.extend(_item(f, report.unknown_policy == "block") for f in report.unknown)
    for error in report.parse_errors:
        if error["introduced"]:
            # Already reported as an introduced finding above.
            continue
        items.append({
            "rule": "parse-error",
            "file": error["path"],
            "line": 0,
            "problem": error["error"],
            "evidence": error["error"],
            "fix": "Fix the syntax error or remove the file from the change.",
            "status": "preexisting",
            "before": "",
            "after": error["error"],
            "blocking": False,
            "suppressed": False,
            "suppression_reason": "",
        })
    return items


def to_markdown(report: VerificationReport) -> str:
    if report.approved:
        return f"## Verification: APPROVED\n\n{report.summary()}\n"
    lines = [
        "## Verification: INDETERMINATE" if report.indeterminate
        else "## Verification: BLOCKED",
        "",
        report.summary(),
        "",
    ]
    sections = [
        ("Introduced violations", report.findings),
        ("Indeterminate results", report.unknown),
        ("Pre-existing findings (not caused by this change)", report.preexisting),
        ("Improvements", report.improvements),
        ("Suppressed findings", report.suppressed),
    ]
    for title, findings in sections:
        if not findings:
            continue
        lines.append(f"### {title}")
        lines.append("")
        for f in findings:
            lines.append(f"#### `{f.rule_id}` — `{f.path}:{f.line}`")
            lines.append(f"- **Problem:** {f.message}")
            if f.evidence:
                lines.append(f"- **Evidence:** `{f.evidence}`")
            if f.before or f.after:
                lines.append(f"- **Before/after:** `{f.before or '?'}` → `{f.after or '?'}`")
            if f.suppression_reason:
                lines.append(f"- **Suppression:** {f.suppression_reason}")
            lines.append(f"- **Fix:** {f.suggestion}")
            lines.append("")
    if report.parse_errors:
        remaining = [e for e in report.parse_errors if not e["introduced"]]
        if remaining:
            lines.append("### Pre-existing parse errors")
            lines.append("")
            for error in remaining:
                lines.append(f"- `{error['path']}`: {error['error']}")
            lines.append("")
    if not report.complete:
        lines.append(
            "_Verification is incomplete: the change introduced an unparseable "
            "file or contains unsupported content. Treat the result as blocked._"
        )
        lines.append("")
    return "\n".join(lines)
