"""Agent loop terminal states and LLM adapter validation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from knowledge_surface.agent.llm_adapter import AgentError, LLMAgent
from knowledge_surface.agent.loop import FeedbackLoop, LoopState, ScriptedAgent
from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import (
    SemanticVerifier,
)
from knowledge_surface.verification.rules import Outcome, Rule, RuleResult


class MarkerRule(Rule):
    id = "marker"
    severity = "error"
    description = "marker"

    def evaluate(self, ctx):
        text = ctx.after_tree.get("m.py", "")
        if "UNKNOWN" in text:
            return RuleResult.unknown(self.id, "unknown marker", path="m.py")
        if "BAD" in text:
            return RuleResult(self.id, Outcome.FAIL, "bad marker", path="m.py", line=1)
        return RuleResult(self.id, Outcome.PASS, "ok")


def _repo(tmp_path: Path, files: dict[str, str] | None = None) -> Path:
    root = tmp_path / "repo"
    root.mkdir(exist_ok=True)
    for rel, content in (files or {"m.py": "ok\n"}).items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _change(before: str, after: str, path: str = "m.py") -> ChangeSet:
    return ChangeSet(files=[FileChange(path=path, before=before, after=after)])


def _complete(payload: object):
    return lambda prompt: json.dumps(payload) if not isinstance(payload, str) else payload


# --- loop ------------------------------------------------------------------


def test_loop_approves_first_candidate(tmp_path):
    root = _repo(tmp_path)
    result = FeedbackLoop(SemanticVerifier([MarkerRule()])).run(
        "task", root, ScriptedAgent([_change("ok\n", "ok\n")])
    )
    assert result.state is LoopState.APPROVED
    assert result.approved
    assert result.iterations == 1
    assert result.final_changes is not None
    assert result.final_report is not None and result.final_report.approved


def test_loop_revises_after_feedback(tmp_path):
    root = _repo(tmp_path)
    result = FeedbackLoop(SemanticVerifier([MarkerRule()])).run(
        "task", root, ScriptedAgent([_change("ok\n", "BAD\n"), _change("ok\n", "ok\n")])
    )
    assert result.state is LoopState.APPROVED
    assert result.iterations == 2
    assert result.attempts[0].feedback
    assert result.final_changes.files[0].after == "ok\n"


def test_loop_rejects_repeated_proposal_without_lying(tmp_path):
    root = _repo(tmp_path)
    result = FeedbackLoop(SemanticVerifier([MarkerRule()])).run(
        "task", root, ScriptedAgent([_change("ok\n", "BAD\n")])
    )
    assert result.state is LoopState.REJECTED
    assert not result.approved
    assert result.final_changes.files[0].after == "BAD\n"
    assert result.final_report is not None and not result.final_report.approved


def test_loop_exhausts_after_budget(tmp_path):
    root = _repo(tmp_path)
    agent = ScriptedAgent([_change("ok\n", "BAD one\n"), _change("ok\n", "BAD two\n")])
    result = FeedbackLoop(SemanticVerifier([MarkerRule()]), max_iterations=2).run(
        "task", root, agent
    )
    assert result.state is LoopState.EXHAUSTED
    assert result.iterations == 2
    assert result.final_changes.files[0].after == "BAD two\n"
    assert result.final_report is not None


def test_loop_indeterminate_when_final_result_is_unknown(tmp_path):
    root = _repo(tmp_path)
    agent = ScriptedAgent([
        _change("ok\n", "x = 'UNKNOWN one'\n"),
        _change("ok\n", "x = 'UNKNOWN two'\n"),
    ])
    result = FeedbackLoop(SemanticVerifier([MarkerRule()]), max_iterations=2).run(
        "task", root, agent
    )
    assert result.state is LoopState.INDETERMINATE
    assert not result.approved


def test_loop_agent_error_on_propose(tmp_path):
    class Broken:
        def propose(self, task, root):
            raise RuntimeError("no model")

        def revise(self, *args):
            raise AssertionError("unreachable")

    result = FeedbackLoop(SemanticVerifier([])).run("task", _repo(tmp_path), Broken())
    assert result.state is LoopState.AGENT_ERROR
    assert result.final_changes is None
    assert "no model" in result.error


def test_loop_agent_error_on_revise_keeps_last_verified_candidate(tmp_path):
    class Broken(ScriptedAgent):
        def revise(self, *args):
            raise RuntimeError("revise failed")

    root = _repo(tmp_path)
    result = FeedbackLoop(SemanticVerifier([MarkerRule()])).run(
        "task", root, Broken([_change("ok\n", "BAD\n")])
    )
    assert result.state is LoopState.AGENT_ERROR
    assert result.final_changes.files[0].after == "BAD\n"
    assert result.final_report is not None


def test_loop_empty_proposal_is_agent_error(tmp_path):
    root = _repo(tmp_path)
    result = FeedbackLoop(SemanticVerifier([])).run("task", root, ScriptedAgent([ChangeSet()]))
    assert result.state is LoopState.AGENT_ERROR
    assert "empty" in result.error


def test_loop_verifier_error_is_reported(tmp_path):
    class ExplodingVerifier:
        def verify(self, root, changes):
            raise RuntimeError("verifier down")

    result = FeedbackLoop(ExplodingVerifier()).run(
        "task", _repo(tmp_path), ScriptedAgent([_change("ok\n", "ok\n")])
    )
    assert result.state is LoopState.VERIFIER_ERROR
    assert "verifier down" in result.error


def test_loop_rejects_zero_iterations():
    with pytest.raises(ValueError):
        FeedbackLoop(SemanticVerifier([]), max_iterations=0)


# --- LLM adapter -----------------------------------------------------------


def _agent(tmp_path: Path, payload, **kwargs) -> LLMAgent:
    root = _repo(tmp_path)
    return root, LLMAgent(_complete(payload), **kwargs)


def test_llm_valid_proposal_reads_before_from_root(tmp_path):
    root, agent = _agent(tmp_path, {"files": [{"path": "m.py", "content": "y = 2\n"}]})
    changes = agent.propose("change it", root)
    assert changes.files[0].before == "ok\n"
    assert changes.files[0].after == "y = 2\n"


def test_llm_accepts_markdown_fences(tmp_path):
    raw = "```json\n" + json.dumps(
        {"files": [{"path": "m.py", "content": "y = 2\n"}]}
    ) + "\n```"
    root, agent = _agent(tmp_path, raw)
    assert agent.propose("task", root).files[0].after == "y = 2\n"


def test_llm_malformed_json_names_the_problem(tmp_path):
    root, agent = _agent(tmp_path, '{"files": [')
    with pytest.raises(AgentError, match="not valid JSON"):
        agent.propose("task", root)


def test_llm_schema_errors_are_explicit(tmp_path):
    cases = [
        {"changes": []},
        {"files": []},
        {"files": [{"path": "m.py"}]},
        {"files": ["m.py"]},
    ]
    for payload in cases:
        root, agent = _agent(tmp_path, payload)
        with pytest.raises(AgentError):
            agent.propose("task", root)


def test_llm_rejects_path_escape(tmp_path):
    root, agent = _agent(tmp_path, {"files": [{"path": "../evil.py", "content": ""}]})
    with pytest.raises(AgentError, match="unsafe path"):
        agent.propose("task", root)


def test_llm_rejects_absolute_path(tmp_path):
    root, agent = _agent(tmp_path, {"files": [{"path": "/etc/passwd", "content": ""}]})
    with pytest.raises(AgentError, match="unsafe path"):
        agent.propose("task", root)


def test_llm_rejects_duplicate_paths(tmp_path):
    payload = {"files": [
        {"path": "m.py", "content": "a\n"},
        {"path": "./m.py", "content": "b\n"},
    ]}
    root, agent = _agent(tmp_path, payload)
    with pytest.raises(AgentError, match="duplicate path"):
        agent.propose("task", root)


def test_llm_supports_deletion(tmp_path):
    root, agent = _agent(tmp_path, {"files": [{"path": "m.py", "delete": True}]})
    changes = agent.propose("task", root)
    assert changes.files[0].after is None
    assert changes.after_tree(root) == {}


def test_llm_deletion_of_missing_file_is_rejected(tmp_path):
    root, agent = _agent(tmp_path, {"files": [{"path": "missing.py", "delete": True}]})
    with pytest.raises(AgentError, match="does not exist"):
        agent.propose("task", root)


def test_llm_supports_rename(tmp_path):
    root, agent = _agent(
        tmp_path,
        {"files": [{"path": "new.py", "old_path": "m.py", "content": "y = 2\n"}]},
    )
    changes = agent.propose("task", root)
    assert changes.files[0].old_path == "m.py"
    assert changes.files[0].before == "ok\n"
    assert set(changes.after_tree(root)) == {"new.py"}


def test_llm_model_exception_is_wrapped(tmp_path):
    def boom(prompt):
        raise TimeoutError("model timeout")

    root = _repo(tmp_path)
    with pytest.raises(AgentError, match="model call failed"):
        LLMAgent(boom).propose("task", root)


def test_llm_non_string_response_is_rejected(tmp_path):
    root = _repo(tmp_path)
    with pytest.raises(AgentError, match="expected str"):
        LLMAgent(lambda prompt: {"files": []}).propose("task", root)


def test_llm_context_is_bounded_and_prioritises_focus(tmp_path):
    files = {f"{c}.py": f"x = '{c}'\n" for c in "abcde"}
    files["m.py"] = "ok\n"
    root = _repo(tmp_path, files)
    captured = {}

    def complete(prompt):
        captured.update(json.loads(prompt))
        return json.dumps({"files": [{"path": "m.py", "content": "y = 2\n"}]})

    agent = LLMAgent(complete, max_files=2, max_bytes=10_000)
    agent.propose("task", root)
    assert len(captured["files"]) == 2
    assert set(captured["files"]) == {"a.py", "b.py"}
    assert captured["omitted"]
    assert "2 of 6 files included" in captured["context_note"]


def test_llm_feedback_paths_are_prioritised(tmp_path):
    files = {f"{c}.py": f"x = '{c}'\n" for c in "abcde"}
    files["m.py"] = "ok\n"
    root = _repo(tmp_path, files)
    captured = {}

    def complete(prompt):
        captured.update(json.loads(prompt))
        return json.dumps({"files": [{"path": "m.py", "content": "y = 2\n"}]})

    current = _change("x = 'a'\n", "x = 'a2'\n", path="a.py")
    agent = LLMAgent(complete, max_files=2, max_bytes=10_000)
    agent.revise("task", root, current, [{"file": "d.py", "path": "d.py"}])
    assert "d.py" in captured["files"]
    assert captured["previous_attempt"][0]["path"] == "a.py"


def test_llm_full_context_includes_every_file(tmp_path):
    files = {f"{c}.py": f"x = '{c}'\n" for c in "abcde"}
    root = _repo(tmp_path, files)
    captured = {}

    def complete(prompt):
        captured.update(json.loads(prompt))
        return json.dumps({"files": [{"path": "a.py", "content": "y = 2\n"}]})

    LLMAgent(complete, full_context=True).propose("task", root)
    assert set(captured["files"]) == set(files)
    assert captured["omitted"] == []


def test_llm_redacts_secret_assignments(tmp_path):
    root = _repo(tmp_path, {"config.py": 'API_KEY = "supersecret"\n'})
    captured = {}

    def complete(prompt):
        captured["prompt"] = prompt
        return json.dumps({"files": [{"path": "config.py", "content": "x = 1\n"}]})

    LLMAgent(complete).propose("task", root)
    assert "supersecret" not in captured["prompt"]
    assert "<redacted>" in captured["prompt"]


def test_llm_stale_before_content_comes_from_current_root(tmp_path):
    root = _repo(tmp_path)
    agent = LLMAgent(_complete({"files": [{"path": "m.py", "content": "new\n"}]}))
    first = agent.propose("task", root)
    assert first.files[0].before == "ok\n"
    (root / "m.py").write_text("changed on disk\n", encoding="utf-8")
    second = agent.propose("task", root)
    assert second.files[0].before == "changed on disk\n"


def test_llm_empty_revision_rejected(tmp_path):
    root, agent = _agent(tmp_path, {"files": []})
    with pytest.raises(AgentError, match="empty revision"):
        agent.propose("task", root)
