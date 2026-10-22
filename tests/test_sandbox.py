"""Behavioural-rule execution: refusal, timeout, output bounds, environment."""

from __future__ import annotations

import time

from knowledge_surface.verification.rules import Outcome
from knowledge_surface.verification.sandbox import MAX_OUTPUT_BYTES, run_behavioral


def _run(snippet: str, *, trusted: bool = True, allow_untrusted: bool = False,
         timeout: float = 5.0, tree: dict[str, str] | None = None):
    return run_behavioral(
        snippet,
        tree if tree is not None else {"m.py": "x = 1\n"},
        trusted=trusted,
        allow_untrusted=allow_untrusted,
        timeout=timeout,
    )


def test_untrusted_is_refused_without_running():
    result = _run(
        "def check():\n    open('executed', 'w').write('yes')\n",
        trusted=False,
    )
    assert result.outcome is Outcome.UNKNOWN
    assert "refused" in result.message


def test_allow_untrusted_opt_in_runs():
    result = _run("def check():\n    assert True\n", trusted=False, allow_untrusted=True)
    assert result.outcome is Outcome.PASS


def test_passing_check():
    result = _run("def check():\n    assert 2 + 2 == 4\n")
    assert result.outcome is Outcome.PASS


def test_failing_check_reports_reason():
    result = _run("def check():\n    raise AssertionError('totals went negative')\n")
    assert result.outcome is Outcome.FAIL
    assert "totals went negative" in result.message


def test_timeout_is_unknown_not_pass():
    start = time.monotonic()
    result = _run("def check():\n    import time\n    time.sleep(10)\n", timeout=0.3)
    elapsed = time.monotonic() - start
    assert result.outcome is Outcome.UNKNOWN
    assert "timed out" in result.message
    assert elapsed < 5


def test_timeout_kills_process_group():
    """A child process must not keep the verifier alive."""
    start = time.monotonic()
    result = _run(
        "def check():\n"
        "    import subprocess, sys, time\n"
        "    subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
        "    time.sleep(30)\n",
        timeout=0.4,
    )
    elapsed = time.monotonic() - start
    assert result.outcome is Outcome.UNKNOWN
    assert elapsed < 5


def test_output_is_bounded():
    result = _run(
        "def check():\n"
        "    print('x' * 100000)\n"
        "    raise AssertionError('done')\n"
    )
    assert result.outcome is Outcome.FAIL
    assert len(result.evidence) <= MAX_OUTPUT_BYTES + 100


def test_environment_is_minimal(monkeypatch):
    monkeypatch.setenv("KS_TEST_SECRET", "must-not-leak")
    result = _run(
        "import os\n"
        "def check():\n"
        "    assert 'KS_TEST_SECRET' not in os.environ\n"
        "    assert 'PYTHONPATH' not in os.environ\n"
    )
    assert result.outcome is Outcome.PASS, result.message


def test_unsafe_tree_path_is_unknown():
    result = _run(
        "def check():\n    assert True\n",
        tree={"../escape.py": "x = 1\n"},
    )
    assert result.outcome is Outcome.UNKNOWN
    assert "cannot stage" in result.message


def test_invalid_timeout_is_unknown():
    for timeout in (0, -1, 301):
        result = _run("def check():\n    assert True\n", timeout=timeout)
        assert result.outcome is Outcome.UNKNOWN
        assert "invalid" in result.message
