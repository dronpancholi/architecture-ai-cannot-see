"""Adversarial patch application and path containment tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

from knowledge_surface.paths import PathError, normalize_repo_path, resolve_in_root
from knowledge_surface.verification.change import ChangeSet, FileChange, PatchError


def _repo(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "repo"
    root.mkdir()
    for rel, content in files.items():
        target = root / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
    return root


def test_multi_hunk_patch_preserves_unchanged_source(tmp_path):
    root = _repo(tmp_path, {"m.py": "".join(f"line{i}\n" for i in range(1, 11))})
    patch = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -2,2 +2,2 @@
 line2
-line3
+LINE3
@@ -8,2 +8,2 @@
 line8
-line9
+LINE9
"""
    changes = ChangeSet.from_patch(patch, root=root)
    after = changes.after_tree(root)["m.py"]
    expected = "".join(
        f"{'LINE3' if i == 3 else 'LINE9' if i == 9 else f'line{i}'}\n"
        for i in range(1, 11)
    )
    assert after == expected
    assert after.count("\n") == 10


def test_multi_file_add_modify_delete_rename(tmp_path):
    root = _repo(tmp_path, {
        "mod.py": "x = 1\ny = 2\n",
        "del.py": "gone = True\n",
        "keep.py": "stable = 1\n",
    })
    root.joinpath("mod.py").write_text("x = 1\ny = 2\nz = 3\n", encoding="utf-8")
    patch = """diff --git a/mod.py b/mod.py
--- a/mod.py
+++ b/mod.py
@@ -1,2 +1,2 @@
 x = 1
-y = 2
+y = 20
diff --git a/new.py b/new.py
new file mode 100644
--- /dev/null
+++ b/new.py
@@ -0,0 +1,2 @@
+a = 1
+b = 2
diff --git a/del.py b/del.py
deleted file mode 100644
--- a/del.py
+++ /dev/null
@@ -1 +0,0 @@
-gone = True
diff --git a/keep.py b/renamed.py
similarity index 100%
rename from keep.py
rename to renamed.py
"""
    changes = ChangeSet.from_patch(patch, root=root)
    tree = changes.after_tree(root)
    assert tree["mod.py"] == "x = 1\ny = 20\nz = 3\n"
    assert tree["new.py"] == "a = 1\nb = 2\n"
    assert "del.py" not in tree
    assert "keep.py" not in tree
    assert tree["renamed.py"] == "stable = 1\n"
    rename = next(f for f in changes.files if f.path == "renamed.py")
    assert rename.old_path == "keep.py"


def test_quoted_paths_with_spaces(tmp_path):
    root = _repo(tmp_path, {"foo bar.py": "x = 1\n"})
    patch = '''diff --git "a/foo bar.py" "b/foo bar.py"
--- "a/foo bar.py"
+++ "b/foo bar.py"
@@ -1 +1 @@
-x = 1
+x = 2
'''
    changes = ChangeSet.from_patch(patch, root=root)
    assert changes.after_tree(root)["foo bar.py"] == "x = 2\n"


def test_no_newline_at_end_of_file(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1"})
    patch = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1 +1 @@
-x = 1
\\ No newline at end of file
+x = 2
\\ No newline at end of file
"""
    changes = ChangeSet.from_patch(patch, root=root)
    assert changes.after_tree(root)["m.py"] == "x = 2"


def test_context_mismatch_is_rejected(tmp_path):
    root = _repo(tmp_path, {"m.py": "x = 1\n"})
    patch = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1 +1 @@
-x = 999
+x = 2
"""
    with pytest.raises(PatchError, match="context mismatch"):
        ChangeSet.from_patch(patch, root=root)


def test_truncated_patch_is_rejected(tmp_path):
    root = _repo(tmp_path, {"m.py": "a\nb\nc\n"})
    patch = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1,3 +1,3 @@
 a
-b
+B
"""
    with pytest.raises(PatchError, match="truncated hunk"):
        ChangeSet.from_patch(patch, root=root)


def test_modified_file_requires_root():
    patch = """diff --git a/m.py b/m.py
--- a/m.py
+++ b/m.py
@@ -1 +1 @@
-x = 1
+x = 2
"""
    with pytest.raises(PatchError, match="root checkout is required"):
        ChangeSet.from_patch(patch)


def test_traversal_paths_rejected():
    for raw in ("../evil.py", "/etc/passwd", "a/../../evil.py", ""):
        with pytest.raises(PathError):
            normalize_repo_path(raw)


def test_duplicate_normalized_paths_rejected(tmp_path):
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    changes = ChangeSet(files=[
        FileChange(path="a.py", before="x = 1\n", after="x = 2\n"),
        FileChange(path="./a.py", before=None, after=""),
    ])
    with pytest.raises(ValueError, match="duplicate"):
        changes.validate(root)


def test_symlink_escape_rejected(tmp_path):
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    outside = tmp_path / "outside"
    outside.mkdir()
    os.symlink(outside, root / "escape")
    with pytest.raises(PathError):
        resolve_in_root(root, "escape/evil.py")


def test_after_tree_does_not_write_paths(tmp_path):
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    changes = ChangeSet(files=[FileChange(path="a.py", before="x = 1\n", after="x = 2\n")])
    tree = changes.after_tree(root)
    assert tree["a.py"] == "x = 2\n"
    assert (root / "a.py").read_text() == "x = 1\n", "verification must not mutate the checkout"


def test_binary_patch_is_incomplete_not_invented(tmp_path):
    root = _repo(tmp_path, {"a.py": "x = 1\n"})
    patch = """diff --git a/a.py b/a.py
index 000..111 100644
Binary files a/a.py and b/a.py differ
"""
    changes = ChangeSet.from_patch(patch, root=root)
    assert not changes.complete
    assert changes.files[0].is_binary
    assert changes.after_tree(root)["a.py"] == "x = 1\n"
