"""Change model and strict unified-diff application.

A change is an explicit before/after pair per file. Patches are applied to a
real base checkout so the verifier sees the *complete* candidate file, not a
concatenation of visible hunk lines.

If a patch cannot be reconstructed faithfully (missing base, binary hunk,
malformed hunk, context mismatch), the parser raises ``PatchError``. It never
invents source.
"""

from __future__ import annotations

import ast
import re
from dataclasses import dataclass, field
from pathlib import Path

from ..paths import iter_python_files, normalize_repo_path, resolve_in_root


class ChangeError(ValueError):
    """Base class for change-model errors."""


class PatchError(ChangeError):
    """The patch is malformed, binary, or does not apply to the base tree."""


@dataclass
class FileChange:
    path: str
    before: str | None
    after: str | None
    old_path: str | None = None       # set for renames/copies
    is_binary: bool = False
    note: str = ""

    @property
    def is_add(self) -> bool:
        return self.before is None and self.after is not None

    @property
    def is_delete(self) -> bool:
        return self.before is not None and self.after is None

    @property
    def is_modify(self) -> bool:
        return self.before is not None and self.after is not None

    @property
    def is_rename(self) -> bool:
        return self.old_path is not None and self.old_path != self.path


@dataclass
class ChangeSet:
    files: list[FileChange] = field(default_factory=list)
    description: str = ""
    complete: bool = True
    warnings: list[str] = field(default_factory=list)

    def touched_paths(self) -> list[str]:
        return [f.path for f in self.files]

    def by_path(self, path: str) -> FileChange | None:
        return next((f for f in self.files if f.path == path), None)

    # --- validation -------------------------------------------------------

    def validate(self, root: str | Path) -> ChangeSet:
        """Normalize and prove every path stays inside *root*.

        Returns a validated copy. Raises ``PathError`` / ``ChangeError`` on
        absolute paths, traversal, duplicates, or ambiguous renames.
        """
        seen: set[str] = set()
        old_seen: set[str] = set()
        files: list[FileChange] = []
        for fc in self.files:
            path = normalize_repo_path(fc.path)
            old_path = normalize_repo_path(fc.old_path) if fc.old_path else None
            if path in seen:
                raise ChangeError(f"duplicate change for path: {path}")
            if old_path:
                if old_path in old_seen:
                    raise ChangeError(f"duplicate rename source: {old_path}")
                old_seen.add(old_path)
            seen.add(path)
            resolve_in_root(root, path)
            if old_path:
                resolve_in_root(root, old_path)
            files.append(FileChange(
                path=path, before=fc.before, after=fc.after,
                old_path=old_path, is_binary=fc.is_binary, note=fc.note,
            ))
        return ChangeSet(
            files=files, description=self.description,
            complete=self.complete, warnings=list(self.warnings),
        )

    # --- materialization --------------------------------------------------

    def after_tree(self, root: str | Path) -> dict[str, str]:
        """Materialize the complete candidate tree as ``path -> content``."""
        validated = self.validate(root)
        tree = _read_python_tree(root)
        for fc in validated.files:
            if fc.is_binary:
                continue
            if fc.old_path and fc.old_path != fc.path:
                tree.pop(fc.old_path, None)
            if fc.after is None:
                tree.pop(fc.path, None)
            else:
                tree[fc.path] = fc.after
        return tree

    def before_tree(self, root: str | Path) -> dict[str, str]:
        return _read_python_tree(root)

    # --- constructors -----------------------------------------------------

    @staticmethod
    def from_contents(path: str, before: str, after: str, description: str = "") -> ChangeSet:
        return ChangeSet(
            files=[FileChange(path=path, before=before, after=after)],
            description=description,
        )

    @staticmethod
    def from_directory_diff(before_root: str | Path, after_root: str | Path) -> ChangeSet:
        b_root, a_root = Path(before_root), Path(after_root)
        b = _read_python_tree(b_root)
        a = _read_python_tree(a_root)
        files: list[FileChange] = []
        for name in sorted(set(b) | set(a)):
            if b.get(name) != a.get(name):
                files.append(FileChange(path=name, before=b.get(name), after=a.get(name)))
        return ChangeSet(files=files)

    @staticmethod
    def from_patch(patch_text: str, root: str | Path | None = None) -> ChangeSet:
        """Parse a git unified diff.

        When *root* is supplied, hunks are applied to the base files in that
        checkout. Modified, deleted, and renamed files require *root* because
        the unchanged source cannot be recovered from the diff alone.
        """
        parsed = _parse_patch(patch_text)
        files: list[FileChange] = []
        warnings: list[str] = []
        complete = True
        for pf in parsed:
            if pf.is_binary:
                complete = False
                warnings.append(f"{pf.path}: binary change cannot be verified")
                files.append(FileChange(
                    path=pf.path, before=None, after=None,
                    old_path=pf.old_path, is_binary=True,
                    note="binary change",
                ))
                continue
            if pf.is_new:
                if root is not None:
                    target = resolve_in_root(root, pf.path)
                    if target.exists():
                        raise PatchError(f"{pf.path}: new-file patch but file already exists")
                after = _apply_new_file(pf)
                files.append(FileChange(path=pf.path, before=None, after=after))
                continue
            if root is None:
                raise PatchError(
                    f"{pf.path}: root checkout is required to reconstruct "
                    "modified/deleted/renamed files"
                )
            src = pf.old_path or pf.path
            before = _read_base(root, src)
            if pf.is_delete:
                files.append(FileChange(path=pf.path, before=before, after=None))
                continue
            after = _apply_hunks(before, pf, pf.path)
            files.append(FileChange(
                path=pf.path, before=before, after=after,
                old_path=pf.old_path if pf.old_path and pf.old_path != pf.path else None,
            ))
        cs = ChangeSet(files=files, complete=complete, warnings=warnings)
        if root is not None:
            cs = cs.validate(root)
        return cs


# --- patch parsing --------------------------------------------------------

@dataclass
class _Hunk:
    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class _ParsedFile:
    path: str
    old_path: str | None = None
    is_new: bool = False
    is_delete: bool = False
    is_binary: bool = False
    old_no_newline: bool = False
    new_no_newline: bool = False
    hunks: list[_Hunk] = field(default_factory=list)


_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")


def _unquote_git_path(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == '"' and raw[-1] == '"':
        body = raw[1:-1]
        out = bytearray()
        i = 0
        while i < len(body):
            ch = body[i]
            if ch == "\\" and i + 1 < len(body):
                nxt = body[i + 1]
                mapping = {"n": 10, "t": 9, "r": 13, '"': 34, "\\": 92}
                if nxt in mapping:
                    out.append(mapping[nxt])
                    i += 2
                    continue
                if nxt in "01234567" and i + 3 < len(body):
                    out.append(int(body[i + 1:i + 4], 8))
                    i += 4
                    continue
            out.extend(ch.encode("utf-8"))
            i += 1
        return out.decode("utf-8", errors="replace")
    return raw


def _strip_prefix(raw: str, prefix: str) -> str:
    raw = _unquote_git_path(raw)
    if raw == "/dev/null":
        return "/dev/null"
    if raw.startswith(prefix):
        return raw[len(prefix):]
    return raw


def _split_diff_header(rest: str) -> tuple[str, str]:
    rest = rest.strip()
    if rest.startswith('"'):
        first, remainder = _read_quoted(rest)
        second, _ = _read_quoted(remainder.strip())
        return _strip_prefix(first, "a/"), _strip_prefix(second, "b/")
    match = re.match(r"^(a/.+?) (b/.+)$", rest)
    if not match:
        raise PatchError(f"malformed 'diff --git' header: {rest!r}")
    return _strip_prefix(match.group(1), "a/"), _strip_prefix(match.group(2), "b/")


def _read_quoted(text: str) -> tuple[str, str]:
    if not text.startswith('"'):
        raise PatchError("expected quoted path")
    body = text[1:]
    out = ['"']
    escaped = False
    for i, ch in enumerate(body):
        out.append(ch)
        if escaped:
            escaped = False
        elif ch == "\\":
            escaped = True
        elif ch == '"':
            return "".join(out), body[i + 1:]
    raise PatchError("unterminated quoted path")


def _parse_patch(patch_text: str) -> list[_ParsedFile]:
    lines = patch_text.splitlines()
    files: list[_ParsedFile] = []
    current: _ParsedFile | None = None
    hunk: _Hunk | None = None
    old_seen = new_seen = 0
    i = 0

    def close_hunk() -> None:
        nonlocal hunk, old_seen, new_seen
        if hunk is not None:
            if old_seen != hunk.old_count or new_seen != hunk.new_count:
                raise PatchError(
                    f"truncated hunk for {current.path if current else '?'}: "
                    f"expected -{hunk.old_count}/+{hunk.new_count}, "
                    f"got -{old_seen}/+{new_seen}"
                )
            current.hunks.append(hunk)  # type: ignore[union-attr]
        hunk, old_seen, new_seen = None, 0, 0

    while i < len(lines):
        line = lines[i]
        if line.startswith("diff --git "):
            close_hunk()
            old, new = _split_diff_header(line[len("diff --git "):])
            current = _ParsedFile(path=new, old_path=old)
            files.append(current)
            i += 1
            continue
        if current is None:
            i += 1
            continue
        if line.startswith("@@"):
            close_hunk()
            match = _HUNK_RE.match(line)
            if not match:
                raise PatchError(f"malformed hunk header: {line!r}")
            hunk = _Hunk(
                old_start=int(match.group(1)),
                old_count=int(match.group(2) or "1"),
                new_start=int(match.group(3)),
                new_count=int(match.group(4) or "1"),
            )
            i += 1
            continue
        if hunk is not None:
            if line.startswith("\\"):
                if hunk.lines:
                    if hunk.lines[-1][0] == "-":
                        current.old_no_newline = True
                    elif hunk.lines[-1][0] == "+":
                        current.new_no_newline = True
                i += 1
                continue
            if not line:
                # An empty context line is a single space in a valid diff.
                kind, text = " ", ""
            else:
                kind, text = line[0], line[1:]
            if kind not in (" ", "+", "-"):
                close_hunk()
                continue
            hunk.lines.append((kind, text))
            if kind in (" ", "-"):
                old_seen += 1
            if kind in (" ", "+"):
                new_seen += 1
            i += 1
            continue
        if line.startswith("new file mode"):
            current.is_new = True
        elif line.startswith("deleted file mode"):
            current.is_delete = True
        elif line.startswith("rename from "):
            current.old_path = _strip_prefix(line[len("rename from "):], "a/")
        elif line.startswith("rename to "):
            current.path = _strip_prefix(line[len("rename to "):], "b/")
        elif line.startswith("copy from "):
            current.old_path = _strip_prefix(line[len("copy from "):], "a/")
            current.is_new = True
        elif line.startswith("copy to "):
            current.path = _strip_prefix(line[len("copy to "):], "b/")
        elif line.startswith("Binary files ") or line.startswith("GIT binary patch"):
            current.is_binary = True
        elif line.startswith("--- "):
            raw = line[4:].split("\t", 1)[0]
            if raw == "/dev/null":
                current.is_new = True
            elif current.old_path is None:
                current.old_path = _strip_prefix(raw, "a/")
        elif line.startswith("+++ "):
            raw = line[4:].split("\t", 1)[0]
            if raw == "/dev/null":
                current.is_delete = True
            else:
                current.path = _strip_prefix(raw, "b/")
        i += 1
    close_hunk()
    if not files:
        raise PatchError("no file changes found in patch")
    for pf in files:
        if pf.is_new and pf.is_delete:
            raise PatchError(f"{pf.path}: patched file is both new and deleted")
    return files


def _read_base(root: str | Path, path: str) -> str:
    target = resolve_in_root(root, path)
    if not target.exists():
        raise PatchError(f"{path}: base file does not exist")
    try:
        return target.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        raise PatchError(f"{path}: base file is not UTF-8: {exc}") from exc


def _apply_new_file(pf: _ParsedFile) -> str:
    lines: list[str] = []
    for hunk in pf.hunks:
        for kind, text in hunk.lines:
            if kind in (" ", "+"):
                lines.append(text)
            elif kind == "-":
                raise PatchError(f"{pf.path}: removal in a new-file hunk")
    content = "\n".join(lines)
    if content and not pf.new_no_newline:
        content += "\n"
    return content


def _apply_hunks(before: str, pf: _ParsedFile, path: str) -> str:
    base = before.splitlines()
    trailing_newline = before.endswith("\n")
    offset = 0
    for n, hunk in enumerate(pf.hunks, 1):
        old_lines = [text for kind, text in hunk.lines if kind in (" ", "-")]
        new_lines = [text for kind, text in hunk.lines if kind in (" ", "+")]
        if len(old_lines) != hunk.old_count or len(new_lines) != hunk.new_count:
            raise PatchError(f"{path}: hunk {n} line counts are inconsistent")
        idx = (hunk.old_start if hunk.old_count == 0 else hunk.old_start - 1) + offset
        actual = base[idx:idx + hunk.old_count]
        if actual != old_lines:
            raise PatchError(
                f"{path}: hunk {n} does not apply at line {hunk.old_start}; "
                f"context mismatch"
            )
        base[idx:idx + hunk.old_count] = new_lines
        offset += hunk.new_count - hunk.old_count
    result = "\n".join(base)
    if pf.new_no_newline:
        result = result.rstrip("\n")
    elif trailing_newline and result:
        result += "\n"
    return result


# --- AST helpers ----------------------------------------------------------

def parse_python(source: str, path: str = "<source>") -> tuple[ast.Module | None, str | None]:
    """Parse Python source, returning ``(tree, error)`` instead of hiding errors."""
    try:
        return ast.parse(source, filename=path), None
    except SyntaxError as exc:
        location = f"{path}:{exc.lineno or 0}:{exc.offset or 0}"
        return None, f"{location}: {exc.msg}"


def parse(source: str | None) -> ast.Module | None:
    """Backward-compatible helper. Prefer :func:`parse_python`."""
    if source is None:
        return None
    tree, _ = parse_python(source)
    return tree


def _read_python_tree(root: str | Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for rel, full in iter_python_files(root):
        try:
            out[rel] = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out
