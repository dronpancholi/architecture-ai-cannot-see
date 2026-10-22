"""Adversarial tests for RequireCallRule scope, targets, and ordering."""

from __future__ import annotations

from pathlib import Path

from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier
from knowledge_surface.verification.rules import RequireCallRule


def _verify(tmp_path: Path, source: str, rule, before: str = ""):
    root = tmp_path / "repo"
    root.mkdir(parents=True)
    (root / "m.py").write_text(before, encoding="utf-8")
    change = ChangeSet(files=[FileChange(path="m.py", before=before, after=source)])
    return SemanticVerifier([rule]).verify(root, change)


def _rule(**kwargs) -> RequireCallRule:
    defaults = dict(id="auth", function=r"^f$", callee="authorize",
                    before_call="delete", required=True)
    defaults.update(kwargs)
    return RequireCallRule(**defaults)


def test_removing_target_fails_by_default(tmp_path):
    before = "def f():\n    authorize()\n    delete()\n"
    report = _verify(tmp_path, "def other():\n    authorize()\n    delete()\n",
                     _rule(), before=before)
    assert not report.approved
    assert "not found" in report.findings[0].message


def test_missing_target_can_be_optional(tmp_path):
    report = _verify(
        tmp_path, "def other():\n    authorize()\n    delete()\n",
        _rule(required=False),
    )
    assert report.approved


def test_nested_function_call_does_not_count(tmp_path):
    source = """
def f():
    def helper():
        authorize()
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved
    assert "does not call authorize" in report.findings[0].message


def test_nested_class_method_call_does_not_count(tmp_path):
    source = """
def f():
    class Helper:
        def run(self):
            authorize()
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved


def test_call_after_protected_operation_fails(tmp_path):
    source = """
def f():
    delete()
    authorize()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved
    assert "dominate" in report.findings[0].message


def test_call_in_one_branch_does_not_dominate_outside(tmp_path):
    source = """
def f():
    if condition:
        authorize()
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved


def test_call_and_protected_in_same_branch_passes(tmp_path):
    source = """
def f():
    if condition:
        authorize()
        delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert report.approved


def test_unconditional_call_before_nested_branch_passes(tmp_path):
    source = """
def f():
    authorize()
    if condition:
        delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert report.approved


def test_authorization_in_if_condition_passes(tmp_path):
    source = """
def f():
    if authorize():
        delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert report.approved


def test_async_function_is_checked(tmp_path):
    source = """
async def f():
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved


def test_owner_scoping_with_same_method_name(tmp_path):
    source = """
class A:
    def verify(self):
        return compare_digest(x, y)
class B:
    def verify(self):
        return x == y
"""
    a = _verify(tmp_path / "a", source,
                _rule(id="a", function=r"^verify$", callee="compare_digest",
                      before_call=None, owner=r"^A$"))
    assert a.approved
    b = _verify(tmp_path / "b", source,
                _rule(id="b", function=r"^verify$", callee="compare_digest",
                      before_call=None, owner=r"^B$"))
    assert not b.approved


def test_multiple_target_definitions_all_must_call(tmp_path):
    source = """
def f():
    authorize()
    delete()
def f():
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert not report.approved


def test_alias_call_counts(tmp_path):
    source = """
import auth as a
def f():
    a.authorize()
    delete()
"""
    report = _verify(tmp_path, source, _rule())
    assert report.approved


def test_comment_and_string_do_not_count(tmp_path):
    source = '''
def f():
    # authorize()
    note = "authorize()"
    delete()
'''
    report = _verify(tmp_path, source, _rule())
    assert not report.approved


def test_required_decorator_missing_target_fails(tmp_path):
    from knowledge_surface.verification.rules import RequiredDecoratorRule

    rule = RequiredDecoratorRule("deco", r"^missing$", "login_required")
    before = "@login_required\ndef missing():\n    pass\n"
    report = _verify(tmp_path, "def other():\n    pass\n", rule, before=before)
    assert not report.approved
    assert "not found" in report.findings[0].message
