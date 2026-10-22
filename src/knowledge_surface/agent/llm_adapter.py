"""LLM-backed agent adapter for the feedback loop.

The loop is agent-agnostic. Inject any ``complete(prompt) -> str`` callable
(OpenAI, Anthropic, a local model, or a deterministic test double). The adapter
asks for full-file replacements as JSON, validates every path through the same
containment checks as the verifier, and bounds the context it sends.

Context selection is explainable: changed files and files named by findings
come first, then files whose imports match a finding, then remaining files by
path. Omitted files are listed in the prompt. ``full_context=True`` disables
the bound for controlled experiments and is deliberately explicit.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..paths import iter_python_files, normalize_repo_path, resolve_in_root
from ..verification.change import ChangeError, ChangeSet, FileChange

SYSTEM = """You are an AI coding agent. You propose file changes as JSON.
Return only a JSON object:
{"files": [{"path": "...", "content": "...", "delete": false, "old_path": null}]}
Use full file contents. Set "delete": true to remove a file. Use "old_path" for
a rename. Never include markdown fences. Respect every architectural invariant
in the feedback; a verifier will reject unsafe changes."""

_SECRET_LINE = re.compile(
    r"(?i)\b(api[_-]?key|secret|token|password|passwd|private[_-]?key)\b\s*[:=]\s*"
    r"([\"'])([^\"']{4,})\2"
)
_SENSITIVE_NAMES = re.compile(
    r"(?i)(^|/)(\.env|id_rsa|id_ed25519|[^/]*(secret|credential|private[_-]?key)[^/]*)$"
)


class AgentError(RuntimeError):
    """The model returned unusable output or tried to escape the repository."""


@dataclass
class ContextLimits:
    max_files: int = 40
    max_bytes: int = 128_000
    max_file_bytes: int = 24_000
    full_context: bool = False


class LLMAgent:
    def __init__(
        self,
        complete: Callable[[str], str],
        *,
        max_files: int = 40,
        max_bytes: int = 128_000,
        max_file_bytes: int = 24_000,
        full_context: bool = False,
        redact_secrets: bool = True,
    ):
        self.complete = complete
        self.limits = ContextLimits(max_files, max_bytes, max_file_bytes, full_context)
        self.redact_secrets = redact_secrets

    # --- public API -------------------------------------------------------

    def propose(self, task: str, root: Path) -> ChangeSet:
        prompt = self._prompt(task, root, None, [])
        return self._parse(self._call(prompt), root)

    def revise(self, task: str, root: Path, current: ChangeSet, feedback: list[dict]) -> ChangeSet:
        prompt = self._prompt(task, root, current, feedback)
        return self._parse(self._call(prompt), root)

    # --- prompt construction ---------------------------------------------

    def _call(self, prompt: str) -> str:
        try:
            raw = self.complete(prompt)
        except Exception as exc:  # model/network failure is not a change
            raise AgentError(f"model call failed: {type(exc).__name__}: {exc}") from exc
        if not isinstance(raw, str):
            raise AgentError(f"model returned {type(raw).__name__}, expected str")
        return raw

    def _prompt(self, task: str, root: Path, current: ChangeSet | None,
                feedback: list[dict]) -> str:
        files = self._select_files(root, current, feedback)
        return json.dumps({
            "system": SYSTEM,
            "task": task,
            "root": str(root),
            "files": files["included"],
            "omitted": files["omitted"],
            "context_note": files["note"],
            "previous_attempt": self._current_attempt(current),
            "feedback": feedback,
        }, indent=2)

    def _select_files(self, root: Path, current: ChangeSet | None,
                      feedback: list[dict]) -> dict:
        all_files: dict[str, str] = {}
        for rel, full in iter_python_files(root):
            try:
                all_files[rel] = full.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
        priority: dict[str, int] = {}
        for index, path in enumerate(_feedback_paths(feedback)):
            priority[path] = min(priority.get(path, 99), index)
        for change in (current.files if current else []):
            priority[change.path] = min(priority.get(change.path, 99), 5)
            if change.old_path:
                priority[change.old_path] = min(priority.get(change.old_path, 99), 5)
        ordered = sorted(all_files, key=lambda p: (priority.get(p, 50), p))

        included: dict[str, str] = {}
        omitted: list[str] = []
        used = 0
        for rel in ordered:
            if _SENSITIVE_NAMES.search(rel):
                omitted.append(rel)
                continue
            try:
                content = all_files[rel]
            except OSError:
                omitted.append(rel)
                continue
            if self.redact_secrets:
                content = _SECRET_LINE.sub(r"\1\2<redacted>\2", content)
            if not self.limits.full_context:
                if len(included) >= self.limits.max_files:
                    omitted.append(rel)
                    continue
                if used + len(content) > self.limits.max_bytes:
                    omitted.append(rel)
                    continue
                if len(content) > self.limits.max_file_bytes:
                    content = content[: self.limits.max_file_bytes] + "\n# ...[truncated]...\n"
            included[rel] = content
            used += len(content)

        note = (
            "full context" if self.limits.full_context
            else f"{len(included)} of {len(all_files)} files included; "
                 f"{len(omitted)} omitted (priority: current changes, finding paths, path order)"
        )
        return {"included": included, "omitted": omitted, "note": note}

    @staticmethod
    def _current_attempt(current: ChangeSet | None) -> list[dict] | None:
        if current is None:
            return None
        return [
            {
                "path": f.path,
                "old_path": f.old_path,
                "content": f.after,
                "deleted": f.after is None,
            }
            for f in current.files
        ]

    # --- response validation ---------------------------------------------

    def _parse(self, raw: str, root: Path) -> ChangeSet:
        data = _load_json(raw)
        if not isinstance(data, dict):
            raise AgentError("response must be a JSON object")
        items = data.get("files")
        if not isinstance(items, list):
            raise AgentError("response must contain a 'files' list")
        if not items:
            raise AgentError("empty revision: 'files' is empty")

        seen: set[str] = set()
        changes: list[FileChange] = []
        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise AgentError(f"files[{index}] must be an object")
            raw_path = item.get("path")
            if not isinstance(raw_path, str) or not raw_path:
                raise AgentError(f"files[{index}].path must be a non-empty string")
            try:
                path = normalize_repo_path(raw_path)
                resolve_in_root(root, path)
            except (ValueError, OSError) as exc:
                raise AgentError(f"unsafe path {raw_path!r}: {exc}") from exc
            if path in seen:
                raise AgentError(f"duplicate path in response: {path}")
            seen.add(path)

            old_path = item.get("old_path")
            if old_path is not None:
                if not isinstance(old_path, str):
                    raise AgentError(f"{path}: old_path must be a string or null")
                try:
                    old_path = normalize_repo_path(old_path)
                    resolve_in_root(root, old_path)
                except (ValueError, OSError) as exc:
                    raise AgentError(f"unsafe old_path {old_path!r}: {exc}") from exc
                if not (root / old_path).is_file():
                    raise AgentError(f"{path}: rename source does not exist: {old_path}")

            deleted = item.get("delete", False)
            if not isinstance(deleted, bool):
                raise AgentError(f"{path}: delete must be a boolean")
            content = item.get("content")
            if deleted and content is not None:
                raise AgentError(f"{path}: deleted file must not include content")
            if not deleted and not isinstance(content, str):
                raise AgentError(f"{path}: content must be a string")
            if deleted and old_path:
                raise AgentError(f"{path}: a rename cannot also delete the target")

            source = old_path or path
            source_file = resolve_in_root(root, source)
            before = source_file.read_text(encoding="utf-8") if source_file.is_file() else None
            after = None if deleted else content
            if before is None and after is None:
                raise AgentError(f"{path}: deletion of a file that does not exist")
            changes.append(FileChange(
                path=path, before=before, after=after,
                old_path=old_path if old_path and old_path != path else None,
            ))

        change_set = ChangeSet(files=changes, description="llm proposal")
        try:
            return change_set.validate(root)
        except (ChangeError, ValueError) as exc:
            raise AgentError(f"invalid change set: {exc}") from exc


def _feedback_paths(feedback: list[dict]) -> list[str]:
    paths: list[str] = []
    for item in feedback:
        path = item.get("path") if isinstance(item, dict) else None
        if isinstance(path, str) and path and path not in paths:
            paths.append(path)
    return paths


def _load_json(raw: str) -> object:
    text = raw.strip()
    if text.startswith("```"):
        # Fenced block: drop the fence line and the closing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        snippet = text[:200].replace("\n", "\\n")
        raise AgentError(
            f"response is not valid JSON ({exc.msg} at line {exc.lineno}): {snippet}"
        ) from exc
