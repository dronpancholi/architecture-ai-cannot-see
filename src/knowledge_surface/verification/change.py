"""Change model: a proposed modification to a source tree.

The verifier reasons over an explicit before/after pair, so it can evaluate
the *effect* of a change rather than merely notice that a file was touched.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class FileChange:
    path: str
    before: str | None
    after: str | None

    @property
    def is_add(self) -> bool:
        return self.before is None and self.after is not None

    @property
    def is_delete(self) -> bool:
        return self.before is not None and self.after is None

    @property
    def is_modify(self) -> bool:
        return self.before is not None and self.after is not None

    def added_lines(self) -> list[tuple[int, str]]:
        if self.before is None:
            return list(enumerate((self.after or "").splitlines(), 1))
        import difflib
        out: list[tuple[int, str]] = []
        for line in difflib.unified_diff(
            self.before.splitlines(), (self.after or "").splitlines(),
            lineterm="", n=0,
        ):
            if line.startswith("+") and not line.startswith("+++"):
                out.append((0, line[1:]))
        return out


@dataclass
class ChangeSet:
    files: list[FileChange] = field(default_factory=list)
    description: str = ""

    def touched_paths(self) -> list[str]:
        return [f.path for f in self.files]

    def by_path(self, path: str) -> FileChange | None:
        return next((f for f in self.files if f.path == path), None)

    def after_tree(self, root: Path) -> dict[str, str]:
        """Materialize the post-change tree as a path -> content mapping.

        Reads the existing tree, then overlays the change set. This lets the
        verifier build a surface from the hypothetical result without writing
        to disk.
        """
        tree: dict[str, str] = {}
        for p in root.rglob("*.py"):
            try:
                tree[str(p.relative_to(root))] = p.read_text()
            except OSError:
                continue
        for fc in self.files:
            if fc.after is None:
                tree.pop(fc.path, None)
            else:
                tree[fc.path] = fc.after
        return tree

    @staticmethod
    def from_patch(patch_text: str) -> ChangeSet:
        """Parse a unified diff (git style) into a ChangeSet."""
        import re
        files: list[FileChange] = []
        current: dict | None = None
        before: list[str] = []
        after: list[str] = []

        def flush() -> None:
            nonlocal current, before, after
            if current is not None:
                files.append(FileChange(
                    path=current["path"],
                    before="\n".join(before) if not current["add"] else None,
                    after="\n".join(after) if not current["delete"] else None,
                ))
            current, before, after = None, [], []

        for line in patch_text.splitlines():
            m = re.match(r"^diff --git a/(.+?) b/(.+)$", line)
            if m:
                flush()
                current = {"path": m.group(2), "add": False, "delete": False}
                continue
            if current is None:
                continue
            if line.startswith("new file mode"):
                current["add"] = True
            elif line.startswith("deleted file mode"):
                current["delete"] = True
            elif line.startswith("@@"):
                continue
            elif line.startswith("+") and not line.startswith("+++"):
                after.append(line[1:])
            elif line.startswith("-") and not line.startswith("---"):
                before.append(line[1:])
            elif line.startswith(" "):
                before.append(line[1:])
                after.append(line[1:])
        flush()
        return ChangeSet(files=files)

    @staticmethod
    def from_contents(path: str, before: str, after: str, description: str = "") -> ChangeSet:
        return ChangeSet(files=[FileChange(path=path, before=before, after=after)], description=description)

    @staticmethod
    def from_directory_diff(before_root: Path, after_root: Path) -> ChangeSet:
        files: list[FileChange] = []
        names = set()
        for root in (before_root, after_root):
            for p in root.rglob("*.py"):
                names.add(str(p.relative_to(root)))
        for name in sorted(names):
            b = before_root / name
            a = after_root / name
            before = b.read_text() if b.exists() else None
            after = a.read_text() if a.exists() else None
            if before != after:
                files.append(FileChange(path=name, before=before, after=after))
        return ChangeSet(files=files)


def parse(source: str | None) -> ast.Module | None:
    if source is None:
        return None
    try:
        return ast.parse(source)
    except SyntaxError:
        return None
