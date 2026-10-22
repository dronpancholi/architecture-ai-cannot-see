"""Per-finding regression tests: a new violation is never hidden by old debt."""

from __future__ import annotations

from pathlib import Path

from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier
from knowledge_surface.verification.rules import (
    ForbiddenCallRule,
    ForbiddenImportRule,
    NoMutableDefaultRule,
    NoOrphanedCallsRule,
    RequireCallRule,
    RequiredDecoratorRule,
    TypeAnnotationRule,
)


def _root(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _change(path: str, before: str | None, after: str | None,
            old_path: str | None = None) -> ChangeSet:
    return ChangeSet(files=[FileChange(
        path=path, before=before, after=after, old_path=old_path,
    )])


def test_existing_and_new_forbidden_import_in_same_file(tmp_path):
    before = "from app.db import Database\n\nx = 1\n"
    root = _root(tmp_path, {"m.py": before})
    after = "from app.cache import Cache\n" + before
    report = SemanticVerifier([
        ForbiddenImportRule("layer", r"^m\.py$", r"app\.(db|cache)"),
    ]).verify(root, _change("m.py", before, after))

    assert not report.approved
    introduced = {f.key for f in report.findings}
    assert "import::app.cache" in introduced
    assert "import::app.cache.Cache" in introduced
    assert all("app.db" not in key for key in introduced)
    # The old import moved down one line but is still the same finding.
    assert {f.key for f in report.preexisting} >= {"import::app.db", "import::app.db.Database"}


def test_existing_violation_in_one_file_and_new_violation_in_another(tmp_path):
    root = _root(tmp_path, {"a.py": "from app.db import Database\n"})
    report = SemanticVerifier([
        ForbiddenImportRule("layer", r".*\.py$", r"app\.db"),
    ]).verify(root, _change("b.py", None, "from app.db import Database\n"))

    assert not report.approved
    assert report.findings and {f.path for f in report.findings} == {"b.py"}
    assert report.preexisting and {f.path for f in report.preexisting} == {"a.py"}


def test_existing_failing_function_plus_new_failing_function(tmp_path):
    before = "def f():\n    delete()\n"
    after = before + "\ndef g():\n    delete()\n"
    root = _root(tmp_path, {"m.py": before})
    rule = RequireCallRule("auth", r"^[fg]$", "authorize", before_call="delete")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert len(report.findings) == 1
    assert "fn::::g#0" in report.findings[0].key
    assert len(report.preexisting) == 1
    assert "fn::::f#0" in report.preexisting[0].key


def test_repaired_old_violation_plus_new_violation(tmp_path):
    before = "def f():\n    delete()\n"
    after = "def f():\n    authorize()\n    delete()\n\ndef g():\n    delete()\n"
    root = _root(tmp_path, {"m.py": before})
    rule = RequireCallRule("auth", r"^[fg]$", "authorize", before_call="delete")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert len(report.findings) == 1 and "fn::::g#0" in report.findings[0].key
    assert len(report.improvements) == 1
    assert "fn::::f#0" in report.improvements[0].key


def test_unchanged_preexisting_violation_does_not_block_unrelated_change(tmp_path):
    root = _root(tmp_path, {
        "a.py": "from app.db import Database\n",
        "b.py": "x = 1\n",
    })
    rule = ForbiddenImportRule("layer", r".*\.py$", r"app\.db")
    report = SemanticVerifier([rule]).verify(root, _change("b.py", "x = 1\n", "x = 2\n"))

    assert report.approved, report.summary()
    assert not report.findings
    assert report.preexisting


def test_file_rename_matches_old_violation_and_still_catches_new_one(tmp_path):
    before = "from app.db import Database\n"
    after = "from app.db import Database\nfrom app.cache import Cache\n"
    root = _root(tmp_path, {"a.py": before})
    rule = ForbiddenImportRule("layer", r".*\.py$", r"app\.(db|cache)")
    report = SemanticVerifier([rule]).verify(
        root, _change("b.py", before, after, old_path="a.py")
    )

    assert not report.approved
    assert {f.key for f in report.findings} >= {"import::app.cache", "import::app.cache.Cache"}
    assert {f.key for f in report.preexisting} >= {"import::app.db", "import::app.db.Database"}
    assert {f.path for f in report.preexisting} == {"b.py"}


def test_function_rename_is_fail_closed_not_silently_safe(tmp_path):
    before = "def f():\n    delete()\n"
    after = "def renamed():\n    delete()\n"
    root = _root(tmp_path, {"m.py": before})
    rule = RequireCallRule("auth", r"^(f|renamed)$", "authorize", before_call="delete")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert report.findings
    assert all("renamed" in f.key for f in report.findings)


def test_module_level_and_function_violations_are_independent(tmp_path):
    before = "def f():\n    eval('1')\n"
    after = "eval('2')\n" + before
    root = _root(tmp_path, {"m.py": before})
    rule = ForbiddenCallRule("no-eval", r"^m\.py$", "eval")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert any("call::module::eval" in f.key for f in report.findings)
    assert any("fn::::f#0" in f.key for f in report.preexisting)


def test_duplicate_function_names_keep_distinct_identities(tmp_path):
    before = "def f():\n    authorize()\n\ndef f():\n    authorize()\n"
    after = "x = 1\n\ndef f():\n    authorize()\n\ndef f():\n    pass\n"
    root = _root(tmp_path, {"m.py": before})
    rule = RequireCallRule("auth", r"^f$", "authorize")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert len(report.findings) == 1
    assert "f#1" in report.findings[0].key
    assert not report.preexisting


def test_type_annotation_and_mutable_defaults_report_each_function(tmp_path):
    before = "def f(a):\n    return a\n"
    after = before + "\ndef g(b=[]):\n    return b\n"
    root = _root(tmp_path, {"m.py": before})
    rules = [TypeAnnotationRule("annotations", skip_private=False), NoMutableDefaultRule()]
    report = SemanticVerifier(rules).verify(root, _change("m.py", before, after))

    assert not report.approved
    by_rule = {f.rule_id: f for f in report.findings}
    assert "annotations" in by_rule and "annotation::fn::::g#0" in by_rule["annotations"].key
    assert "no-mutable-default" in by_rule
    assert "mutable::fn::::g#0::b" in by_rule["no-mutable-default"].key


def test_orphaned_calls_report_every_caller(tmp_path):
    before = (
        "def helper():\n    return 1\n\n"
        "def a():\n    helper()\n\n"
        "def b():\n    helper()\n"
    )
    after = "def a():\n    helper()\n\ndef b():\n    helper()\n"
    root = _root(tmp_path, {"m.py": before})
    report = SemanticVerifier([NoOrphanedCallsRule()]).verify(
        root, _change("m.py", before, after)
    )

    assert not report.approved
    assert len(report.findings) == 2
    assert {f.key for f in report.findings} == {
        "orphan::fn::::a#0::helper", "orphan::fn::::b#0::helper",
    }


def test_required_decorator_reports_every_function(tmp_path):
    before = (
        "@login_required\ndef a():\n    pass\n\n"
        "@login_required\ndef b():\n    pass\n"
    )
    after = "def a():\n    pass\n\ndef b():\n    pass\n"
    root = _root(tmp_path, {"m.py": before})
    rule = RequiredDecoratorRule("deco", r"^[ab]$", "login_required")
    report = SemanticVerifier([rule]).verify(root, _change("m.py", before, after))

    assert not report.approved
    assert len(report.findings) == 2
    assert {f.key for f in report.findings} == {
        "decorator::fn::::a#0::login_required",
        "decorator::fn::::b#0::login_required",
    }
