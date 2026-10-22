"""Benchmark runner: measure semantic verification on labelled scenarios."""

from __future__ import annotations

import argparse
import json
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from knowledge_surface.verification.engine import SemanticVerifier

try:
    from .scenarios import FIXTURES, Scenario, scenarios
except ImportError:  # direct script execution
    from scenarios import FIXTURES, Scenario, scenarios


@dataclass
class Result:
    scenario: str
    category: str
    expected_blocked: bool
    predicted_blocked: bool
    summary: str
    findings: list[dict] = field(default_factory=list)
    unknown: int = 0
    complete: bool = True

    @property
    def correct(self) -> bool:
        return self.expected_blocked == self.predicted_blocked

    @property
    def tp(self) -> int:
        return int(self.expected_blocked and self.predicted_blocked)

    @property
    def fp(self) -> int:
        return int(not self.expected_blocked and self.predicted_blocked)

    @property
    def tn(self) -> int:
        return int(not self.expected_blocked and not self.predicted_blocked)

    @property
    def fn(self) -> int:
        return int(self.expected_blocked and not self.predicted_blocked)


def run_scenario(s: Scenario) -> Result:
    with tempfile.TemporaryDirectory(prefix="ks-bench-") as td:
        root = Path(td) / "repo"
        shutil.copytree(FIXTURES / s.fixture, root)
        if s.setup:
            s.setup(root)
        changes = s.make_changes(root)
        verifier = SemanticVerifier(s.rules)
        report = verifier.verify(root, changes)
        return Result(
            scenario=s.name, category=s.category,
            expected_blocked=s.expected_blocked,
            predicted_blocked=not report.approved,
            summary=report.summary(),
            findings=[f.to_dict() for f in report.findings],
            unknown=len(report.unknown),
            complete=report.complete,
        )


def aggregate(results: list[Result]) -> dict:
    tp = sum(r.tp for r in results)
    fp = sum(r.fp for r in results)
    tn = sum(r.tn for r in results)
    fn = sum(r.fn for r in results)
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
    accuracy = (tp + tn) / len(results) if results else 0.0
    fpr = fp / (fp + tn) if (fp + tn) else 0.0
    return {
        "scenarios": len(results), "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        "unknown": sum(r.unknown for r in results),
        "incomplete": sum(not r.complete for r in results),
        "precision": round(precision, 4), "recall": round(recall, 4),
        "f1": round(f1, 4), "accuracy": round(accuracy, 4),
        "false_positive_rate": round(fpr, 4),
    }


def to_markdown(results: list[Result], agg: dict) -> str:
    lines = [
        "# Benchmark Results",
        "",
        "Ground truth: a scenario labelled *block* introduces an architectural violation;",
        "a scenario labelled *allow* is a safe refactor or pre-existing debt.",
        "",
        "## Aggregate",
        "",
        "| Metric | Value |",
        "|---|---|",
        f"| Scenarios | {agg['scenarios']} |",
        f"| True positives | {agg['tp']} |",
        f"| False positives | {agg['fp']} |",
        f"| True negatives | {agg['tn']} |",
        f"| False negatives | {agg['fn']} |",
        f"| Precision | {agg['precision']:.2%} |",
        f"| Recall | {agg['recall']:.2%} |",
        f"| F1 | {agg['f1']:.2%} |",
        f"| Accuracy | {agg['accuracy']:.2%} |",
        f"| False-positive rate | {agg['false_positive_rate']:.2%} |",
        f"| Unknown results | {agg.get('unknown', 0)} |",
        f"| Incomplete scenarios | {agg.get('incomplete', 0)} |",
        "",
        "## Per scenario",
        "",
        "| Scenario | Category | Expected | Predicted | Correct |",
        "|---|---|---|---|---|",
    ]
    for r in results:
        mark = "✅" if r.correct else "❌"
        lines.append(
            f"| `{r.scenario}` | {r.category} | {'block' if r.expected_blocked else 'allow'} "
            f"| {'block' if r.predicted_blocked else 'allow'} | {mark} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser()
    out = Path(__file__).resolve().parent
    parser.add_argument("--json", type=Path, default=out / "results.json")
    parser.add_argument("--md", type=Path, default=out / "RESULTS.md")
    args = parser.parse_args()

    results = [run_scenario(s) for s in scenarios()]
    agg = aggregate(results)
    args.json.write_text(json.dumps({"aggregate": agg, "results": [r.__dict__ for r in results]}, indent=2))
    args.md.write_text(to_markdown(results, agg))
    print(json.dumps(agg, indent=2))
    for r in results:
        if not r.correct:
            print(f"MISMATCH {r.scenario}: expected={r.expected_blocked} predicted={r.predicted_blocked} {r.summary}")


if __name__ == "__main__":
    main()
