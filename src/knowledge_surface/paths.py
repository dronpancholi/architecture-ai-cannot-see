"""Path safety and source-tree walking.

Every path that comes from a diff, a rule file, or a model must pass through
this module before it reaches the filesystem. Containment is checked on the
resolved path (following symlinks), not on string prefixes.
"""

from __future__ import annotations

import os
from collections.abc import Iterable, Iterator
from pathlib import Path, PurePosixPath

DEFAULT_EXCLUDES = {
    ".git", ".hg", ".svn", "__pycache__", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", ".tox", ".venv", "venv", "env", "node_modules", "build",
    "dist", ".eggs", ".idea", ".vscode",
}


class PathError(ValueError):
    """A path is absolute, escapes the root, or is otherwise unsafe."""


def normalize_repo_path(path: str | PurePosixPath) -> str:
    """Return a safe, normalized POSIX path relative to a repository root."""
    raw = str(path)
    if not raw or "\x00" in raw:
        raise PathError("empty path or NUL byte")
    if "\\" in raw:
        raise PathError(f"backslash is not allowed in repository paths: {raw!r}")
    p = PurePosixPath(raw)
    if p.is_absolute():
        raise PathError(f"absolute paths are not allowed: {raw!r}")
    parts = p.parts
    if any(part in ("..", ".") for part in parts):
        raise PathError(f"parent or current-directory component in path: {raw!r}")
    if not parts:
        raise PathError(f"empty path: {raw!r}")
    return p.as_posix()


def resolve_in_root(root: str | Path, path: str | PurePosixPath) -> Path:
    """Resolve *path* under *root* and prove it stays inside *root*.

    The check is performed after resolving symlinks, so a symlinked directory
    cannot redirect a write outside the root.
    """
    rel = normalize_repo_path(path)
    base = Path(root).resolve()
    candidate = (base / rel).resolve()
    if candidate != base and base not in candidate.parents:
        raise PathError(f"path escapes repository root: {rel!r}")
    return candidate


def safe_write(root: str | Path, rel: str, content: str) -> Path:
    """Write *content* to a validated path under *root* (used for temp trees)."""
    target = resolve_in_root(root, rel)
    target.parent.mkdir(parents=True, exist_ok=True)
    # Re-check after mkdir: a pre-existing symlink in the tree cannot redirect.
    if target.exists() and target.is_symlink():
        raise PathError(f"refusing to write through symlink: {rel!r}")
    target.write_text(content, encoding="utf-8")
    return target


def _is_excluded(rel: str, excludes: set[str]) -> bool:
    parts = set(PurePosixPath(rel).parts)
    if parts & excludes:
        return True
    name = PurePosixPath(rel).name
    return any(name.endswith(suffix) for suffix in (".pyc", ".pyo", ".so", ".dylib"))


def iter_python_files(
    root: str | Path,
    excludes: Iterable[str] | None = None,
    max_file_bytes: int = 2_000_000,
) -> Iterator[tuple[str, Path]]:
    """Yield ``(relative_posix_path, absolute_path)`` for safe Python files.

    Directory symlinks are not followed. File symlinks are yielded only when
    their target stays inside *root*. Excluded directories and oversized files
    are skipped.
    """
    base = Path(root).resolve()
    excluded = set(DEFAULT_EXCLUDES if excludes is None else excludes)
    for dirpath, dirnames, filenames in os.walk(base, followlinks=False):
        rel_dir = Path(dirpath).relative_to(base).as_posix()
        dirnames[:] = sorted(
            d for d in dirnames
            if d not in excluded
            and not (Path(dirpath) / d).is_symlink()
        )
        for name in sorted(filenames):
            if not name.endswith(".py"):
                continue
            full = Path(dirpath) / name
            rel = name if rel_dir == "." else f"{rel_dir}/{name}"
            if _is_excluded(rel, excluded):
                continue
            try:
                resolved = full.resolve()
                if resolved != base and base not in resolved.parents:
                    continue
                if not resolved.is_file():
                    continue
                if resolved.stat().st_size > max_file_bytes:
                    continue
            except OSError:
                continue
            yield rel, full


def read_tree(
    root: str | Path,
    max_file_bytes: int = 2_000_000,
) -> dict[str, str]:
    """Read every safe Python file under *root* into a relative-path map."""
    out: dict[str, str] = {}
    for rel, full in iter_python_files(root, max_file_bytes=max_file_bytes):
        try:
            out[rel] = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
    return out
