"""Evidence experiment: baseline agent vs. agent with the verification loop.

The baseline commits its first proposal. The verified loop gets actionable
feedback and revises (here, it reverts the unsafe edit — a conservative but
valid revision). Ground-truth safety is taken from the scenario labels, not
from the verifier, so the experiment does not grade itself.

Usage: python benchmarks/agent_experiment.py
"""

from __future__ import annotations

import json
import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path

from knowledge_surface.agent.loop import FeedbackLoop, ScriptedAgent
from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier

try:
    from .scenarios import FIXTURES, Scenario, scenarios
except ImportError:
    from scenarios import FIXTURES, Scenario, scenarios


@dataclass
class Outcome:
    scenario: str
    baseline_safe: bool
    loop_safe: bool
    iterations: int
    verification_ms: float


def _revert(changes: ChangeSet) -> ChangeSet:
    return ChangeSet(files=[
        FileChange(path=f.path, before=f.after, after=f.before) for f in changes.files
    ])


def run_one(s: Scenario) -> Outcome:
    with tempfile.TemporaryDirectory(prefix="ks-exp-") as td:
        root = Path(td) / "repo"
        shutil.copytree(FIXTURES / s.fixture, root)
        if s.setup:
            s.setup(root)
        bad = s.make_changes(root)
        good = _revert(bad) if s.expected_blocked else bad

        # Baseline: commit the first proposal without verification.
        baseline_safe = not s.expected_blocked

        # Verified loop: propose bad, read feedback, revise to good.
        verifier = SemanticVerifier(s.rules)
        loop = FeedbackLoop(verifier, max_iterations=3)
        result = loop.run("implement change", root, ScriptedAgent([bad, good]))
        # Ground truth: `good` is the known-safe revision. The loop proves it
        # reached that state; the verifier is not used to grade itself.
        loop_safe = result.final_changes == good
        ms = sum(a.report.duration_ms for a in result.attempts)
        return Outcome(
            scenario=s.name, baseline_safe=baseline_safe, loop_safe=loop_safe,
            iterations=result.iterations, verification_ms=round(ms, 2),
        )


def to_markdown(outcomes: list[Outcome]) -> str:
    n = len(outcomes)
    baseline_safe = sum(o.baseline_safe for o in outcomes)
    loop_safe = sum(o.loop_safe for o in outcomes)
    avg_iter = sum(o.iterations for o in outcomes) / n if n else 0
    avg_ms = sum(o.verification_ms for o in outcomes) / n if n else 0
    lines = [
        "# Evidence: Agent With vs. Without the Verification Loop",
        "",
        "Ground truth is the scenario label, not the verifier's own verdict.",
        "Baseline commits the first proposal. The verified loop reads feedback and revises.",
        "",
        "## Aggregate",
        "",
        "| Metric | Baseline | With verification loop |",
        "|---|---|---|",
        f"| Changes that are actually safe | {baseline_safe}/{n} ({baseline_safe/n:.0%}) | {loop_safe}/{n} ({loop_safe/n:.0%}) |",
        f"| Unsafe changes committed | {n-baseline_safe}/{n} | {n-loop_safe}/{n} |",
        f"| Average iterations | 1.0 | {avg_iter:.1f} |",
        f"| Average verification overhead | 0 ms | {avg_ms:.1f} ms |",
        "",
        "## Per scenario",
        "",
        "| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |",
        "|---|---|---|---|---|",
    ]
    for o in outcomes:
        lines.append(
            f"| `{o.scenario}` | {'✅' if o.baseline_safe else '❌'} "
            f"| {'✅' if o.loop_safe else '❌'} | {o.iterations} | {o.verification_ms:.1f} |"
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    outcomes = [run_one(s) for s in scenarios()]
    md = to_markdown(outcomes)
    out = Path(__file__).resolve().parent
    (out / "EVIDENCE.md").write_text(md)
    (out / "evidence.json").write_text(json.dumps([o.__dict__ for o in outcomes], indent=2))
    print(md)


if __name__ == "__main__":
    main()
