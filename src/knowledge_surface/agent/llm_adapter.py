"""LLM-backed agent adapter for the feedback loop.

The loop is agent-agnostic; this adapter shows how to plug in a real model.
It asks the model for a JSON object describing full-file replacements, which
is robust to parse and lets the verifier reason over the exact post-change
tree. Inject any ``complete(prompt) -> str`` callable (OpenAI, Anthropic,
local model) so this module stays dependency-free.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

from ..verification.change import ChangeSet, FileChange

SYSTEM = """You are an AI coding agent. You propose file changes as JSON.
Return only a JSON object: {"files": [{"path": "...", "content": "..."}]}.
Never include markdown fences. Respect the architectural invariants in the feedback."""


class LLMAgent:
    def __init__(self, complete: Callable[[str], str], read_root: Path | None = None):
        self.complete = complete
        self.read_root = read_root

    def _prompt(self, task: str, root: Path, current: ChangeSet | None, feedback: list[dict]) -> str:
        files = {}
        for p in sorted(root.rglob("*.py")):
            if "__pycache__" in p.parts:
                continue
            files[str(p.relative_to(root))] = p.read_text()
        return json.dumps({
            "system": SYSTEM,
            "task": task,
            "files": files,
            "previous_attempt": [f.__dict__ for f in current.files] if current else None,
            "feedback": feedback,
        })

    def _parse(self, raw: str) -> ChangeSet:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = raw.split("```")[1]
            raw = raw.split("\n", 1)[1] if "\n" in raw else raw
        data = json.loads(raw)
        changes: list[FileChange] = []
        for f in data.get("files", []):
            path = f["path"]
            after = f["content"]
            before = None
            if self.read_root and (self.read_root / path).exists():
                before = (self.read_root / path).read_text()
            changes.append(FileChange(path=path, before=before, after=after))
        return ChangeSet(files=changes)

    def propose(self, task: str, root: Path) -> ChangeSet:
        return self._parse(self.complete(self._prompt(task, root, None, [])))

    def revise(self, task: str, root: Path, current: ChangeSet, feedback: list[dict]) -> ChangeSet:
        return self._parse(self.complete(self._prompt(task, root, current, feedback)))
