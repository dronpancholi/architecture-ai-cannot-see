"""Extract a Knowledge Surface from Python source code.

This is the cold-start path: it recovers the First Architecture (what is in
the files) with high confidence. The Second Architecture must be supplied by
humans or inferred; this extractor is honest about that.

Extraction is bounded and observable:

* generated/vendor/build directories are excluded by default;
* directory symlinks are not followed and file symlinks must stay inside the
  root;
* parse failures become UNKNOWN module entities plus diagnostics, never silent
  omissions;
* unresolved imports become UNKNOWN external modules, not invented edges.
"""

from __future__ import annotations

import ast
import time
from pathlib import Path, PurePosixPath

from ..paths import DEFAULT_EXCLUDES, iter_python_files
from ..representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    Location,
    Provenance,
    RelationKind,
    Relationship,
)
from ..representation.knowledge_surface import KnowledgeSurface


class PythonASTExtractor:
    def __init__(
        self,
        root: str | Path,
        *,
        excludes: set[str] | None = None,
        max_file_bytes: int = 2_000_000,
        max_files: int = 20_000,
    ):
        self.root = Path(root)
        self.excludes = set(DEFAULT_EXCLUDES if excludes is None else excludes)
        self.max_file_bytes = max_file_bytes
        self.max_files = max_files
        self._trees: dict[str, ast.Module] = {}
        self._errors: dict[str, str] = {}
        self.stats: dict = {}

    def build(self, name: str = "knowledge-surface") -> KnowledgeSurface:
        start = time.perf_counter()
        ks = KnowledgeSurface(name=name)
        module_ids: dict[str, str] = {}
        discovered = list(iter_python_files(
            self.root, self.excludes, max_file_bytes=self.max_file_bytes,
        ))
        truncated = len(discovered) > self.max_files
        files = discovered[: self.max_files]
        unresolved = 0

        for rel, full in files:
            self._parse(full, rel)
            mid = Entity.make_id(EntityKind.MODULE, rel)
            module_ids[rel] = mid
            error = self._errors.get(rel)
            ks.add_entity(Entity(
                id=mid, kind=EntityKind.MODULE, name=rel,
                location=Location(file=rel, start_line=1, end_line=self._line_count(full, rel)),
                confidence=Confidence.UNKNOWN if error else Confidence.KNOWN,
                provenance=Provenance(created_by="extractor:ast", source=rel),
                attributes={"parse_error": error} if error else {},
            ))

        # Map dotted module names, including packages (``pkg/__init__.py``).
        module_names: dict[str, str] = {}
        for rel, mid in module_ids.items():
            module_names[_dotted(rel)] = mid

        for rel, _ in files:
            mid = module_ids[rel]
            tree = self._trees.get(rel)
            if tree is None:
                continue
            self._extract_file(tree, rel, mid, ks)
            unresolved += self._extract_imports(tree, rel, mid, module_names, ks)

        self.stats = {
            "files_discovered": len(discovered),
            "files_parsed": len(self._trees),
            "parse_failures": len(self._errors),
            "unresolved_imports": unresolved,
            "truncated": truncated,
            "max_files": self.max_files,
            "max_file_bytes": self.max_file_bytes,
            "entities": len(ks.entities()),
            "relationships": len(ks.relationships()),
            "duration_ms": round((time.perf_counter() - start) * 1000, 2),
        }
        ks.diagnostics = {
            key: value for key, value in self.stats.items() if key != "duration_ms"
        }
        ks.diagnostics.update({
            "parse_errors": [
                {"path": p, "error": e} for p, e in sorted(self._errors.items())
            ],
            "excludes": sorted(self.excludes),
        })
        return ks

    # --- parsing ----------------------------------------------------------

    def _parse(self, full: Path, rel: str) -> None:
        try:
            source = full.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            self._errors[rel] = f"{rel}: cannot read: {exc}"
            return
        try:
            self._trees[rel] = ast.parse(source, filename=rel)
        except (SyntaxError, ValueError) as exc:
            line = getattr(exc, "lineno", 0) or 0
            offset = getattr(exc, "offset", 0) or 0
            message = getattr(exc, "msg", str(exc))
            self._errors[rel] = f"{rel}:{line}:{offset}: {message}"

    def _line_count(self, full: Path, rel: str) -> int:
        tree = self._trees.get(rel)
        if tree is not None:
            return max((getattr(n, "end_lineno", 0) or 0) for n in ast.walk(tree)) if tree.body else 0
        return 0

    # --- entities ---------------------------------------------------------

    def _extract_file(self, tree: ast.Module, rel: str, mid: str, ks: KnowledgeSurface) -> None:
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fid = Entity.make_id(EntityKind.FUNCTION, f"{node.name}@{node.lineno}", rel)
                ks.add_entity(Entity(
                    id=fid, kind=EntityKind.FUNCTION, name=node.name,
                    location=Location(file=rel, start_line=node.lineno,
                                      end_line=getattr(node, "end_lineno", node.lineno)),
                    confidence=Confidence.KNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel),
                    attributes={"docstring": ast.get_docstring(node) or "",
                                "async": isinstance(node, ast.AsyncFunctionDef)},
                ))
                self._add_rel(ks, Relationship(
                    id=Relationship.make_id(mid, RelationKind.IMPLEMENTS, fid),
                    source=mid, target=fid, kind=RelationKind.IMPLEMENTS,
                    confidence=Confidence.KNOWN, evidence="top-level function",
                ))
            elif isinstance(node, ast.ClassDef):
                cid = Entity.make_id(EntityKind.CLASS, f"{node.name}@{node.lineno}", rel)
                ks.add_entity(Entity(
                    id=cid, kind=EntityKind.CLASS, name=node.name,
                    location=Location(file=rel, start_line=node.lineno,
                                      end_line=getattr(node, "end_lineno", node.lineno)),
                    confidence=Confidence.KNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel),
                    attributes={"docstring": ast.get_docstring(node) or ""},
                ))
                self._add_rel(ks, Relationship(
                    id=Relationship.make_id(mid, RelationKind.IMPLEMENTS, cid),
                    source=mid, target=cid, kind=RelationKind.IMPLEMENTS,
                    confidence=Confidence.KNOWN, evidence="top-level class",
                ))
                self._extract_class_members(node, rel, cid, ks)

    def _extract_class_members(self, node: ast.ClassDef, rel: str, cid: str,
                               ks: KnowledgeSurface, prefix: str = "") -> None:
        owner = f"{prefix}{node.name}"
        for sub in node.body:
            if isinstance(sub, ast.ClassDef):
                self._extract_nested_class(sub, rel, node.name, ks)
            elif isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{owner}.{sub.name}"
                mid2 = Entity.make_id(EntityKind.FUNCTION, f"{name}@{sub.lineno}", rel)
                ks.add_entity(Entity(
                    id=mid2, kind=EntityKind.FUNCTION, name=name,
                    location=Location(file=rel, start_line=sub.lineno,
                                      end_line=getattr(sub, "end_lineno", sub.lineno)),
                    confidence=Confidence.KNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel),
                    attributes={"docstring": ast.get_docstring(sub) or "",
                                "owner_class": owner,
                                "async": isinstance(sub, ast.AsyncFunctionDef)},
                ))
                self._add_rel(ks, Relationship(
                    id=Relationship.make_id(cid, RelationKind.IMPLEMENTS, mid2),
                    source=cid, target=mid2, kind=RelationKind.IMPLEMENTS,
                    confidence=Confidence.KNOWN, evidence="method",
                ))

    def _extract_nested_class(self, node: ast.ClassDef, rel: str, parent: str,
                              ks: KnowledgeSurface) -> None:
        name = f"{parent}.{node.name}"
        cid = Entity.make_id(EntityKind.CLASS, f"{name}@{node.lineno}", rel)
        ks.add_entity(Entity(
            id=cid, kind=EntityKind.CLASS, name=name,
            location=Location(file=rel, start_line=node.lineno,
                              end_line=getattr(node, "end_lineno", node.lineno)),
            confidence=Confidence.KNOWN,
            provenance=Provenance(created_by="extractor:ast", source=rel),
            attributes={"docstring": ast.get_docstring(node) or "", "nested": True},
        ))
        self._extract_class_members(node, rel, cid, ks, prefix=f"{parent}.")

    # --- imports ----------------------------------------------------------

    def _extract_imports(self, tree: ast.Module, rel: str, src_mid: str,
                         module_names: dict[str, str], ks: KnowledgeSurface) -> int:
        unresolved = 0
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    unresolved += self._add_import_rel(
                        src_mid, alias.name, module_names, ks, rel,
                        evidence=f"import {alias.name}" + (f" as {alias.asname}" if alias.asname else ""),
                    )
            elif isinstance(node, ast.ImportFrom):
                base = _resolve_relative(rel, node.level, node.module or "")
                if not base:
                    continue
                unresolved += self._add_import_rel(
                    src_mid, base, module_names, ks, rel,
                    evidence=f"from {'.' * node.level}{node.module or ''} import ...",
                )
                for alias in node.names:
                    if alias.name == "*":
                        continue
                    unresolved += self._add_import_rel(
                        src_mid, f"{base}.{alias.name}", module_names, ks, rel,
                        evidence=f"from {'.' * node.level}{node.module or ''} import {alias.name}",
                    )
        return unresolved

    def _add_import_rel(self, src_mid: str, modname: str,
                        module_names: dict[str, str], ks: KnowledgeSurface,
                        rel: str, evidence: str) -> int:
        target_mid = module_names.get(modname)
        unresolved = 0
        if target_mid is None:
            target_mid = Entity.make_id(EntityKind.MODULE, f"<external:{modname}>")
            unresolved = 1
            if ks.entity(target_mid) is None:
                ks.add_entity(Entity(
                    id=target_mid, kind=EntityKind.MODULE, name=f"<external:{modname}>",
                    confidence=Confidence.UNKNOWN,
                    provenance=Provenance(
                        created_by="extractor:ast", source=rel,
                        rationale="unresolved import; may be external or dynamically defined",
                    ),
                    attributes={"external": True},
                ))
        rid = Relationship.make_id(src_mid, RelationKind.IMPORTS, target_mid)
        if not ks.has_relationship(rid):
            self._add_rel(ks, Relationship(
                id=rid, source=src_mid, target=target_mid, kind=RelationKind.IMPORTS,
                confidence=Confidence.KNOWN if target_mid in module_names.values() else Confidence.INFERRED,
                evidence=evidence,
            ))
        return unresolved

    @staticmethod
    def _add_rel(ks: KnowledgeSurface, rel: Relationship) -> None:
        if not ks.has_relationship(rel.id):
            ks.add_relationship(rel)


def _dotted(rel: str) -> str:
    path = PurePosixPath(rel)
    parts = list(path.parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _resolve_relative(rel: str, level: int, module: str) -> str:
    if level == 0:
        return module
    package = list(PurePosixPath(rel).parent.parts)
    # level 1 is the current package, level 2 the parent, ...
    keep = len(package) - (level - 1)
    if keep < 0:
        return ""
    base = package[:keep]
    if module:
        base.extend(module.split("."))
    return ".".join(base)
