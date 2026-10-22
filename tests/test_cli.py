"""CLI contracts: exit codes, JSON output, and error handling."""

from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from knowledge_surface.cli import cli


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _surface(tmp_path: Path, root: Path, name: str = "ks.json") -> Path:
    out = tmp_path / name
    result = CliRunner().invoke(cli, ["build", str(root), "-o", str(out)])
    assert result.exit_code == 0, result.output
    return out


def _rules(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "rules.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    return path


def _patch(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "change.diff"
    path.write_text(text, encoding="utf-8")
    return path


def test_build_and_inspect_json(tmp_path):
    root = _repo(tmp_path, {"m.py": "def f():\n    return 1\n"})
    out = _surface(tmp_path, root)
    data = json.loads(out.read_text())
    assert data["schema_version"] == 1
    result = CliRunner().invoke(cli, ["inspect", str(out), "--json"])
    assert result.exit_code == 0
    assert json.loads(result.output)["name"] == "knowledge-surface"


def test_inspect_rejects_newer_schema(tmp_path):
    path = tmp_path / "ks.json"
    path.write_text(json.dumps({"schema_version": 99, "name": "x"}), encoding="utf-8")
    result = CliRunner().invoke(cli, ["inspect", str(path)])
    assert result.exit_code == 2
    assert "unsupported schema_version" in result.output


def test_query_match_and_miss(tmp_path):
    root = _repo(tmp_path, {"m.py": "def find_me():\n    pass\n"})
    out = _surface(tmp_path, root)
    hit = CliRunner().invoke(cli, ["query", str(out), "find_me"])
    assert hit.exit_code == 0
    assert "find_me" in hit.output
    miss = CliRunner().invoke(cli, ["query", str(out), "nope"])
    assert miss.exit_code == 1


def test_check_remove_unknown_entity_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out = _surface(tmp_path, root)
    result = CliRunner().invoke(cli, ["check", str(out), "missing-id"])
    assert result.exit_code == 2
    assert "unknown entity" in result.output


def test_check_add_requires_spec(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out = _surface(tmp_path, root)
    result = CliRunner().invoke(cli, ["check", str(out), "--action", "add"])
    assert result.exit_code == 2
    assert "--spec" in result.output


def test_check_add_accepts_valid_spec(tmp_path):
    root = _repo(tmp_path, {"m.py": "def f():\n    pass\n"})
    out = _surface(tmp_path, root)
    spec = tmp_path / "entity.json"
    spec.write_text(json.dumps({
        "id": "new-id", "kind": "function", "name": "new_function",
    }), encoding="utf-8")
    result = CliRunner().invoke(
        cli, ["check", str(out), "--action", "add", "--spec", str(spec)]
    )
    assert result.exit_code == 0, result.output
    assert "approved: True" in result.output


def test_check_remove_known_entity(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out = _surface(tmp_path, root)
    data = json.loads(out.read_text())
    entity_id = next(e["id"] for e in data["entities"] if e["kind"] == "module")
    result = CliRunner().invoke(cli, ["check", str(out), entity_id])
    assert result.exit_code == 0, result.output


def test_verify_approved(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "forbidden_call", "id": "no-eval",
        "scope": r"^m\.py$", "callee": "eval",
    }]})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 0, result.output
    assert "APPROVED" in result.output


def test_verify_blocked(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+eval('1')\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "forbidden_call", "id": "no-eval",
        "scope": r"^m\.py$", "callee": "eval",
    }]})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 1, result.output
    assert "BLOCKED" in result.output


def test_verify_unknown_exit_code_and_json(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "behavioral", "id": "untrusted",
        "snippet": "def check():\n    assert True\n",
    }]})
    json_out = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli,
        ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
         "--json-out", str(json_out)],
    )
    assert result.exit_code == 3, result.output
    report = json.loads(json_out.read_text())
    assert report["unknown"]
    assert report["unknown_policy"] == "block"


def test_verify_warn_policy_allows_unknown(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "behavioral", "id": "untrusted",
        "snippet": "def check():\n    assert True\n",
    }]})
    result = CliRunner().invoke(
        cli,
        ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
         "--unknown-policy", "warn"],
    )
    assert result.exit_code == 0, result.output


def test_verify_invalid_patch_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, "this is not a diff\n")
    rules = _rules(tmp_path, {"rules": []})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 2
    assert "invalid patch" in result.output


def test_verify_invalid_rules_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": [{"type": "not-a-rule"}]})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 2
    assert "unknown rule" in result.output.replace("\n", " ")


def test_drift_detects_loss_and_can_fail(tmp_path):
    before_root = _repo(tmp_path / "before", {
        "m.py": "# INVARIANT: money must be decimal\nx = 1\n",
    })
    after_root = _repo(tmp_path / "after", {"m.py": "x = 1\n"})
    before = _surface(tmp_path, before_root, "before.json")
    after = _surface(tmp_path, after_root, "after.json")

    result = CliRunner().invoke(cli, ["drift", str(before), str(after), "--json"])
    assert result.exit_code == 0
    assert "invariant-loss" in result.output

    failed = CliRunner().invoke(
        cli, ["drift", str(before), str(after), "--fail-on-drift"]
    )
    assert failed.exit_code == 1
