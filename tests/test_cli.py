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


def test_inspect_malformed_json_is_input_error(tmp_path):
    path = tmp_path / "ks.json"
    path.write_text("{not json", encoding="utf-8")
    result = CliRunner().invoke(cli, ["inspect", str(path)])
    assert result.exit_code == 2
    assert "cannot read" in result.output


def test_build_output_write_error_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    result = CliRunner().invoke(cli, ["build", str(root), "-o", str(out_dir)])
    assert result.exit_code == 2
    assert "cannot write" in result.output


def test_build_skips_unsupported_and_reports_parse_failures(tmp_path):
    root = _repo(tmp_path, {
        "m.py": "x = 1\n",
        "notes.txt": "not python\n",
        "broken.py": "def broken(:\n",
    })
    out = _surface(tmp_path, root)
    result = CliRunner().invoke(cli, ["inspect", str(out)])
    assert result.exit_code == 0, result.output
    assert "parse failure" in result.output


def test_query_match_and_miss(tmp_path):
    root = _repo(tmp_path, {"m.py": "def find_me():\n    pass\n"})
    out = _surface(tmp_path, root)
    hit = CliRunner().invoke(cli, ["query", str(out), "find_me"])
    assert hit.exit_code == 0
    assert "find_me" in hit.output
    as_json = CliRunner().invoke(cli, ["query", str(out), "find_me", "--json"])
    assert as_json.exit_code == 0
    assert json.loads(as_json.output)[0]["name"] == "find_me"
    miss = CliRunner().invoke(cli, ["query", str(out), "nope"])
    assert miss.exit_code == 1


def test_inspect_text_and_report(tmp_path):
    root = _repo(tmp_path, {"m.py": "# INVARIANT: never lose money\ndef f():\n    pass\n"})
    out = _surface(tmp_path, root)
    inspected = CliRunner().invoke(cli, ["inspect", str(out)])
    assert inspected.exit_code == 0, inspected.output
    assert "Confidence:" in inspected.output
    reported = CliRunner().invoke(cli, ["report", str(out)])
    assert reported.exit_code == 0, reported.output
    assert "## Invariants" in reported.output
    assert "## Unknowns" in reported.output


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
    redundant = CliRunner().invoke(
        cli, ["check", str(out), "ignored-id", "--action", "add", "--spec", str(spec)]
    )
    assert redundant.exit_code == 0, redundant.output
    assert "ignored for --action add" in redundant.output


def test_check_invalid_entity_spec_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out = _surface(tmp_path, root)
    spec = tmp_path / "entity.json"
    spec.write_text("{not json", encoding="utf-8")
    result = CliRunner().invoke(
        cli, ["check", str(out), "--action", "add", "--spec", str(spec)]
    )
    assert result.exit_code == 2
    assert "invalid entity spec" in result.output


def test_check_remove_requires_entity_id(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    out = _surface(tmp_path, root)
    result = CliRunner().invoke(cli, ["check", str(out)])
    assert result.exit_code == 2
    assert "requires an entity_id" in result.output


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


def test_verify_reports_new_and_old_violations_separately(tmp_path):
    root = _repo(tmp_path, {
        "m.py": "x = 1\nfrom app.db import Database\n",
    })
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1,2 +1,3 @@\n"
        "+from app.cache import Cache\n"
        " x = 1\n"
        " from app.db import Database\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "forbidden_import", "id": "layer",
        "source": r"^m\.py$", "forbidden": r"app\.(db|cache)",
    }]})
    json_out = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
              "--json-out", str(json_out)],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(json_out.read_text())
    assert any("app.cache" in f["key"] for f in report["findings"])
    assert any("app.db" in f["key"] for f in report["preexisting"])
    assert all("app.db" not in f["key"] for f in report["findings"])


def test_verify_catches_new_violation_in_a_different_file(tmp_path):
    root = _repo(tmp_path, {"a.py": "from app.db import Database\n"})
    patch = _patch(tmp_path, (
        "diff --git a/b.py b/b.py\nnew file mode 100644\n--- /dev/null\n+++ b/b.py\n"
        "@@ -0,0 +1 @@\n+from app.db import Database\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "forbidden_import", "id": "layer",
        "source": r".*\.py$", "forbidden": r"app\.db",
    }]})
    json_out = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
              "--json-out", str(json_out)],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(json_out.read_text())
    assert report["findings"] and {f["path"] for f in report["findings"]} == {"b.py"}
    assert report["preexisting"] and {f["path"] for f in report["preexisting"]} == {"a.py"}


def test_verify_require_call_new_failing_function_exits_one(tmp_path):
    root = _repo(tmp_path, {"m.py": "def f():\n    delete()\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1,2 +1,4 @@\n"
        " def f():\n"
        "     delete()\n"
        "+def g():\n"
        "+    delete()\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "require_call", "id": "auth", "function": r"^[fg]$",
        "callee": "authorize", "before_call": "delete",
    }]})
    json_out = tmp_path / "report.json"
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
              "--json-out", str(json_out)],
    )
    assert result.exit_code == 1, result.output
    report = json.loads(json_out.read_text())
    assert len(report["findings"]) == 1
    assert "g#0" in report["findings"][0]["key"]
    assert report["preexisting"] and "f#0" in report["preexisting"][0]["key"]


def test_verify_pre_existing_violation_does_not_block_safe_file(tmp_path):
    root = _repo(tmp_path, {
        "a.py": "from app.db import Database\n",
        "b.py": "x = 1\n",
    })
    patch = _patch(tmp_path, (
        "diff --git a/b.py b/b.py\n--- a/b.py\n+++ b/b.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": [{
        "type": "forbidden_import", "id": "layer",
        "source": r".*\.py$", "forbidden": r"app\.db",
    }]})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 0, result.output
    assert "APPROVED" in result.output


def test_verify_invalid_patch_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, "this is not a diff\n")
    rules = _rules(tmp_path, {"rules": []})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 2
    assert "invalid patch" in result.output


def test_verify_unreadable_patch_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = tmp_path / "change.diff"
    patch.write_bytes(b"\xff\xfe\x00")
    rules = _rules(tmp_path, {"rules": []})
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules)]
    )
    assert result.exit_code == 2
    assert "cannot read patch" in result.output


def test_verify_json_out_write_error_is_input_error(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = _patch(tmp_path, (
        "diff --git a/m.py b/m.py\n--- a/m.py\n+++ b/m.py\n"
        "@@ -1 +1 @@\n-x = 1\n+x = 2\n"
    ))
    rules = _rules(tmp_path, {"rules": []})
    out_dir = tmp_path / "reports"
    out_dir.mkdir()
    result = CliRunner().invoke(
        cli, ["verify", str(root), "--patch", str(patch), "--rules", str(rules),
              "--json-out", str(out_dir)],
    )
    assert result.exit_code == 2
    assert "cannot write" in result.output


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
