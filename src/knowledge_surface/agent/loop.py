"""The AI-agent feedback loop.

propose -> verify -> actionable feedback -> revise -> verify again.

The loop is agent-agnostic. Any object implementing ``propose`` / ``revise``
can drive it; the included ``ScriptedAgent`` makes the experiment
deterministic and reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from ..verification.change import ChangeSet
from ..verification.engine import SemanticVerifier, VerificationReport
from ..verification.feedback import feedback_items


@dataclass
class Attempt:
    iteration: int
    changes: ChangeSet
    report: VerificationReport
    feedback: list[dict] = field(default_factory=list)


@dataclass
class LoopResult:
    approved: bool
    iterations: int
    attempts: list[Attempt]
    final_changes: ChangeSet

    def summary(self) -> str:
        status = "approved" if self.approved else "unresolved"
        return f"{status} after {self.iterations} iteration(s)"


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
        self.verifier = verifier
        self.max_iterations = max_iterations

    def run(self, task: str, root: Path, agent: Agent) -> LoopResult:
        attempts: list[Attempt] = []
        changes = agent.propose(task, root)
        for i in range(self.max_iterations):
            report = self.verifier.verify(root, changes)
            fb = feedback_items(report)
            attempts.append(Attempt(i, changes, report, fb))
            if report.approved:
                return LoopResult(True, i + 1, attempts, changes)
            changes = agent.revise(task, root, changes, fb)
        return LoopResult(False, self.max_iterations, attempts, changes)


class Baseline:
    """An agent with no verifier: commits its first proposal."""

    def __init__(self, agent: Agent):
        self.agent = agent

    def run(self, task: str, root: Path) -> ChangeSet:
        return self.agent.propose(task, root)
