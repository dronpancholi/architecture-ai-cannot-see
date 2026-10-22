"""The AI-agent feedback loop.

propose -> verify -> actionable feedback -> revise -> verify again.

The loop is agent-agnostic. Any object implementing ``propose`` / ``revise``
can drive it; the included ``ScriptedAgent`` keeps unit tests deterministic.

Terminal states are explicit. In particular, the returned ``final_changes``
always belongs to the last *verified* attempt. A revision that was produced but
never verified is never presented as the result of verification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Protocol

from ..verification.change import ChangeSet
from ..verification.engine import SemanticVerifier, VerificationReport
from ..verification.feedback import feedback_items


class LoopState(StrEnum):
    APPROVED = "approved"
    REJECTED = "rejected"                 # no progress / agent repeated itself
    EXHAUSTED = "exhausted"               # iteration budget reached
    AGENT_ERROR = "agent_error"           # propose/revise failed
    VERIFIER_ERROR = "verifier_error"     # verification raised
    INDETERMINATE = "indeterminate"       # final result was unknown


@dataclass
class Attempt:
    iteration: int
    changes: ChangeSet
    report: VerificationReport
    feedback: list[dict] = field(default_factory=list)


@dataclass
class LoopResult:
    state: LoopState
    iterations: int
    attempts: list[Attempt]
    final_changes: ChangeSet | None
    final_report: VerificationReport | None = None
    error: str = ""

    @property
    def approved(self) -> bool:
        return self.state is LoopState.APPROVED

    def summary(self) -> str:
        return f"{self.state.value} after {self.iterations} iteration(s)" + (
            f": {self.error}" if self.error else ""
        )


class Agent(Protocol):
    def propose(self, task: str, root: Path) -> ChangeSet:
        ...

    def revise(self, task: str, root: Path, current: ChangeSet, feedback: list[dict]) -> ChangeSet:
        ...


class ScriptedAgent:
    """Deterministic agent: yields a fixed sequence of candidate changes.

    The first candidate models an agent working without architectural memory.
    Later candidates model a revised proposal after reading verifier feedback.
    """

    def __init__(self, attempts: list[ChangeSet], name: str = "scripted"):
        if not attempts:
            raise ValueError("ScriptedAgent needs at least one attempt")
        self.attempts = attempts
        self.name = name
        self._i = 0

    def propose(self, task: str, root: Path) -> ChangeSet:
        self._i = 0
        return self.attempts[0]

    def revise(self, task: str, root: Path, current: ChangeSet, feedback: list[dict]) -> ChangeSet:
        self._i = min(self._i + 1, len(self.attempts) - 1)
        return self.attempts[self._i]


class FeedbackLoop:
    def __init__(self, verifier: SemanticVerifier, max_iterations: int = 5):
        if max_iterations < 1:
            raise ValueError("max_iterations must be at least 1")
        self.verifier = verifier
        self.max_iterations = max_iterations

    def run(self, task: str, root: Path, agent: Agent) -> LoopResult:
        attempts: list[Attempt] = []
        try:
            changes = agent.propose(task, root)
        except Exception as exc:
            return LoopResult(
                LoopState.AGENT_ERROR, 0, attempts, None,
                error=f"propose failed: {type(exc).__name__}: {exc}",
            )
        if not changes.files:
            return LoopResult(
                LoopState.AGENT_ERROR, 0, attempts, changes,
                error="agent proposed an empty change set",
            )

        final_report: VerificationReport | None = None
        for i in range(self.max_iterations):
            try:
                report = self.verifier.verify(root, changes)
            except Exception as exc:
                return LoopResult(
                    LoopState.VERIFIER_ERROR, i, attempts, changes,
                    error=f"verification failed: {type(exc).__name__}: {exc}",
                )
            final_report = report
            feedback = feedback_items(report)
            attempts.append(Attempt(i, changes, report, feedback))
            if report.approved:
                return LoopResult(
                    LoopState.APPROVED, i + 1, attempts, changes, report,
                )
            if i == self.max_iterations - 1:
                break

            try:
                revised = agent.revise(task, root, changes, feedback)
            except Exception as exc:
                return LoopResult(
                    LoopState.AGENT_ERROR, i + 1, attempts, changes, report,
                    error=f"revise failed: {type(exc).__name__}: {exc}",
                )
            if revised is None or not revised.files:
                return LoopResult(
                    LoopState.AGENT_ERROR, i + 1, attempts, changes, report,
                    error="agent returned an empty revision",
                )
            if _same_changes(changes, revised):
                return LoopResult(
                    LoopState.REJECTED, i + 1, attempts, changes, report,
                    error="agent repeated the same proposal",
                )
            changes = revised

        state = LoopState.INDETERMINATE if (
            final_report is not None and final_report.indeterminate
            and not final_report.findings
        ) else LoopState.EXHAUSTED
        return LoopResult(
            state, self.max_iterations, attempts, changes, final_report,
        )


def _same_changes(a: ChangeSet, b: ChangeSet) -> bool:
    def key(cs: ChangeSet) -> tuple:
        return tuple(sorted(
            (f.path, f.old_path, f.before, f.after) for f in cs.files
        ))

    return key(a) == key(b)


class Baseline:
    """An agent with no verifier: commits its first proposal."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def run(self, task: str, root: Path) -> ChangeSet:
        return self.agent.propose(task, root)
