"""Benchmark reproducibility: pinned checkouts and anchor failures."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

import external  # noqa: E402


def _git_repo(tmp_path: Path) -> tuple[Path, str]:
    repo = tmp_path / "origin"
    repo.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=repo, check=True)
    (repo / "m.py").write_text("x = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-qm", "one"], cwd=repo, check=True)
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()
    return repo, sha


def test_checkout_uses_exact_pin(tmp_path):
    repo, sha = _git_repo(tmp_path)
    target = external.Target("local", str(repo), sha, [])
    dest = tmp_path / "checkout"
    head = external.checkout(target, dest)
    assert head == sha
    assert (dest / "m.py").read_text() == "x = 1\n"


def test_checkout_rejects_mismatched_head(tmp_path, monkeypatch):
    repo, sha = _git_repo(tmp_path)
    target = external.Target("local", str(repo), sha, [])
    dest = tmp_path / "checkout"

    real_git = external._git

    def fake_git(args, check=True):
        result = real_git(args, check=check)
        if args[:3] == ["-C", str(dest), "rev-parse"]:
            result.stdout = "0" * 40 + "\n"
        return result

    monkeypatch.setattr(external, "_git", fake_git)
    with pytest.raises(external.BenchmarkError, match="expected pinned"):
        external.checkout(target, dest)


def test_checkout_fails_on_unknown_pin(tmp_path):
    repo, _ = _git_repo(tmp_path)
    target = external.Target("local", str(repo), "f" * 40, [])
    with pytest.raises(external.BenchmarkError):
        external.checkout(target, tmp_path / "checkout")


def test_verify_checkout_rejects_wrong_head(tmp_path):
    repo, _ = _git_repo(tmp_path)
    target = external.Target("local", str(repo), "0" * 40, [])
    with pytest.raises(external.BenchmarkError, match="--path HEAD"):
        external._verify_checkout(target, repo)


def test_verify_checkout_rejects_non_git_directory(tmp_path):
    target = external.Target("local", "unused", "0" * 40, [])
    with pytest.raises(external.BenchmarkError, match="not a git checkout"):
        external._verify_checkout(target, tmp_path)


def test_missing_anchor_fails_instead_of_skipping(tmp_path):
    repo, sha = _git_repo(tmp_path)
    scenario = external.ExtScenario(
        "no-anchor", "introduced-violation", True, [],
        "m.py", "this text is absent", "replacement",
    )
    target = external.Target("local", str(repo), sha, [scenario])
    with pytest.raises(external.BenchmarkError, match="anchor not found"):
        external.run_target(target, repo)


def test_target_selection_requires_unambiguous_match():
    targets = external.targets()
    with pytest.raises(external.BenchmarkError, match="choose one of"):
        external._select(targets, "does-not-exist")


def test_pinned_targets_are_declared():
    for target in external.targets():
        assert len(target.pin) == 40
        assert all(c in "0123456789abcdef" for c in target.pin)
        assert target.repo.startswith("https://")
