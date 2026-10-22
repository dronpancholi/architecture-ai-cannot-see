"""Tri-state verification: PASS / FAIL / UNKNOWN and before/after policy."""

from __future__ import annotations

from pathlib import Path

import pytest

from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier
from knowledge_surface.verification.rules import Outcome, Rule, RuleResult


class ContentRule(Rule):
    """Deterministic test rule driven by markers in the candidate file."""

    def __init__(self, rule_id: str = "content-rule"):
        self.id = rule_id
        self.severity = "error"
        self.description = "marker rule"

    def evaluate(self, ctx):
        text = ctx.after_tree.get("m.py", "")
        if "UNKNOWN" in text:
            return RuleResult.unknown(self.id, "marker says unknown", path="m.py")
        if "BAD" in text:
            return RuleResult(self.id, Outcome.FAIL, "marker says bad",
                              path="m.py", line=1)
        return RuleResult(self.id, Outcome.PASS, "ok")


def _root(tmp_path: Path, content: str) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    (root / "m.py").write_text(content, encoding="utf-8")
    return root


def _change(before: str, after: str) -> ChangeSet:
    return ChangeSet(files=[FileChange(path="m.py", before=before, after=after)])


@pytest.mark.parametrize(
    ("before", "after", "approved", "bucket"),
    [
        ("ok", "ok", True, None),
        ("ok", "BAD", False, "findings"),
        ("BAD", "BAD", True, "preexisting"),
        ("BAD", "ok", True, "improvements"),
        ("UNKNOWN", "BAD", False, "unknown"),
        ("ok", "UNKNOWN", False, "unknown"),
        ("UNKNOWN", "UNKNOWN", False, "unknown"),
        ("UNKNOWN", "ok", True, "improvements"),
        ("BAD", "UNKNOWN", False, "unknown"),
    ],
)
def test_before_after_matrix(tmp_path, before, after, approved, bucket):
    root = _root(tmp_path, before)
    report = SemanticVerifier([ContentRule()]).verify(root, _change(before, after))
    assert report.approved is approved, report.summary()
    if bucket is None:
        assert not report.findings and not report.unknown
    else:
        assert getattr(report, bucket), report.to_dict()


def test_unknown_is_never_classified_as_preexisting(tmp_path):
    root = _root(tmp_path, "UNKNOWN")
    report = SemanticVerifier([ContentRule()]).verify(root, _change("UNKNOWN", "BAD"))
    assert not report.approved
    assert report.unknown
    assert not report.preexisting
    assert report.unknown[0].before == "unknown"
    assert report.unknown[0].after == "fail"


def test_unknown_policy_warn_records_but_allows(tmp_path):
    root = _root(tmp_path, "ok")
    report = SemanticVerifier([ContentRule()], unknown_policy="warn").verify(
        root, _change("ok", "UNKNOWN")
    )
    assert report.approved
    assert report.unknown
    assert report.unknown_policy == "warn"


def test_allowlist_records_reason_for_unknown(tmp_path):
    from knowledge_surface.verification.rules import Allowlist

    root = _root(tmp_path, "ok")
    report = SemanticVerifier(
        [ContentRule()],
        Allowlist([("content-rule", "m.py", "accepted risk")]),
    ).verify(root, _change("ok", "UNKNOWN"))
    assert report.approved
    assert report.suppressed
    assert report.suppressed[0].suppression_reason == "accepted risk"
    assert report.suppressed[0].suppressed


def test_invalid_unknown_policy_rejected():
    with pytest.raises(ValueError, match="unknown_policy"):
        SemanticVerifier([], unknown_policy="whatever")


def test_rule_exception_becomes_unknown(tmp_path):
    class Exploding(Rule):
        id = "boom"
        severity = "error"
        description = "boom"

        def evaluate(self, ctx):
            raise RuntimeError("rule bug")

    root = _root(tmp_path, "ok")
    report = SemanticVerifier([Exploding()]).verify(root, _change("ok", "ok"))
    assert not report.approved
    assert report.unknown
    assert "rule bug" in report.unknown[0].message


def test_parse_error_in_changed_file_blocks(tmp_path):
    root = _root(tmp_path, "x = 1\n")
    bad = "def broken(:\n"
    report = SemanticVerifier([ContentRule()]).verify(root, _change("x = 1\n", bad))
    assert not report.approved
    assert not report.complete
    assert report.parse_errors
    assert report.parse_errors[0]["introduced"] is True
    assert any(f.rule_id == "parse-error" for f in report.unknown)


def test_parse_error_in_unchanged_file_is_visible_and_policy_controlled(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "m.py").write_text("x = 1\n", encoding="utf-8")
    (root / "broken.py").write_text("def broken(:\n", encoding="utf-8")
    change = _change("x = 1\n", "x = 2\n")

    blocked = SemanticVerifier([ContentRule()]).verify(root, change)
    assert not blocked.approved
    assert not blocked.complete
    assert blocked.parse_errors[0]["introduced"] is False
    assert blocked.preexisting

    warned = SemanticVerifier([ContentRule()], unknown_policy="warn").verify(root, change)
    assert warned.approved


def test_deterministic_ordering(tmp_path):
    class Many(Rule):
        id = "many"
        severity = "error"
        description = "many"

        def evaluate(self, ctx):
            return RuleResult(self.id, Outcome.FAIL, "bad", path="m.py", line=1)

    root = _root(tmp_path, "ok")
    report = SemanticVerifier([Many(), Many()]).verify(root, _change("ok", "ok"))
    keys = [(f.path, f.line, f.rule_id, f.status) for f in report.findings]
    assert keys == sorted(keys)
