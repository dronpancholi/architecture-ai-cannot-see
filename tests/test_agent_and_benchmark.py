"""Tests for the agent feedback loop and benchmark integrity."""

import sys
from pathlib import Path

from knowledge_surface import ChangeSet, FileChange, RequireCallRule, SemanticVerifier
from knowledge_surface.agent.loop import FeedbackLoop, ScriptedAgent

ROOT = Path(__file__).resolve().parents[1]


def test_loop_reaches_approved_state():
    import shutil
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "repo"
        shutil.copytree(ROOT / "benchmarks/fixtures/auth_service", root)
        before = (root / "auth/service.py").read_text()
        bad = before.replace('        self.authorize(actor, "delete")\n        return self.repo.delete(user_id)',
                             '        return self.repo.delete(user_id)')
        good = before
        ch_bad = ChangeSet(files=[FileChange(path="auth/service.py", before=before, after=bad)])
        ch_good = ChangeSet(files=[FileChange(path="auth/service.py", before=before, after=good)])
        rules = [RequireCallRule("delete-auth", r"^delete_account$", "authorize", before_call="delete")]
        loop = FeedbackLoop(SemanticVerifier(rules), max_iterations=3)
        result = loop.run("remove account", root, ScriptedAgent([ch_bad, ch_good]))
        assert result.approved
        assert result.iterations == 2
        assert result.attempts[0].report.approved is False


def test_benchmark_meets_quality_bar():
    sys.path.insert(0, str(ROOT / "benchmarks"))
    from runner import aggregate, run_scenario
    from scenarios import scenarios

    results = [run_scenario(s) for s in scenarios()]
    agg = aggregate(results)
    assert agg["recall"] >= 0.9, agg
    assert agg["precision"] >= 0.9, agg
    assert agg["false_positive_rate"] <= 0.1, agg
    assert agg["accuracy"] >= 0.9, agg
