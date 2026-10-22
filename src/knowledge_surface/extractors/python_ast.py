"""Extract a Knowledge Surface from Python source code.

This is the cold-start path: it recovers the First Architecture (what is in
the files) with high confidence. The Second Architecture must be supplied
by humans or inferred; this extractor is honest about that.
"""

from __future__ import annotations

import ast
from pathlib import Path

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
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def build(self, name: str = "knowledge-surface") -> KnowledgeSurface:
        ks = KnowledgeSurface(name=name)
        files = sorted(self.root.rglob("*.py"))
        # First pass: modules + top-level defs
        module_ids: dict[str, str] = {}
        for f in files:
            rel = str(f.relative_to(self.root))
            if "__pycache__" in rel:
                continue
            mid = Entity.make_id(EntityKind.MODULE, rel)
            ks.add_entity(Entity(
                id=mid, kind=EntityKind.MODULE, name=rel,
                location=Location(file=rel, start_line=1, end_line=self._line_count(f)),
                confidence=Confidence.KNOWN,
                provenance=Provenance(created_by="extractor:ast", source=rel),
            ))
            module_ids[rel] = mid
            self._extract_file(f, rel, mid, ks)
        # Second pass: resolve imports into relationships (best-effort, honest)
        for f in files:
            rel = str(f.relative_to(self.root))
            if "__pycache__" in rel:
                continue
            self._extract_imports(f, rel, module_ids, ks)
        return ks

    def _line_count(self, f: Path) -> int:
        try:
            return len(f.read_text().splitlines())
        except OSError:
            return 0

    def _extract_file(self, f: Path, rel: str, mid: str, ks: KnowledgeSurface) -> None:
        try:
            tree = ast.parse(f.read_text(), filename=rel)
        except SyntaxError:
            return
        for node in ast.iter_child_nodes(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                fid = Entity.make_id(EntityKind.FUNCTION, node.name, rel)
                ks.add_entity(Entity(
                    id=fid, kind=EntityKind.FUNCTION, name=node.name,
                    location=Location(file=rel, start_line=node.lineno, end_line=getattr(node, "end_lineno", node.lineno)),
                    confidence=Confidence.KNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel),
                    attributes={"docstring": ast.get_docstring(node) or ""},
                ))
                ks.add_relationship(Relationship(
                    id=Relationship.make_id(mid, RelationKind.IMPLEMENTS, fid),
                    source=mid, target=fid, kind=RelationKind.IMPLEMENTS,
                    confidence=Confidence.KNOWN, evidence="top-level function",
                ))
            elif isinstance(node, ast.ClassDef):
                cid = Entity.make_id(EntityKind.CLASS, node.name, rel)
                ks.add_entity(Entity(
                    id=cid, kind=EntityKind.CLASS, name=node.name,
                    location=Location(file=rel, start_line=node.lineno, end_line=getattr(node, "end_lineno", node.lineno)),
                    confidence=Confidence.KNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel),
                    attributes={"docstring": ast.get_docstring(node) or ""},
                ))
                ks.add_relationship(Relationship(
                    id=Relationship.make_id(mid, RelationKind.IMPLEMENTS, cid),
                    source=mid, target=cid, kind=RelationKind.IMPLEMENTS,
                    confidence=Confidence.KNOWN, evidence="top-level class",
                ))
                for sub in node.body:
                    if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        mid2 = Entity.make_id(EntityKind.FUNCTION, f"{node.name}.{sub.name}", rel)
                        ks.add_entity(Entity(
                            id=mid2, kind=EntityKind.FUNCTION, name=f"{node.name}.{sub.name}",
                            location=Location(file=rel, start_line=sub.lineno, end_line=getattr(sub, "end_lineno", sub.lineno)),
                            confidence=Confidence.KNOWN,
                            provenance=Provenance(created_by="extractor:ast", source=rel),
                            attributes={"docstring": ast.get_docstring(sub) or "", "owner_class": node.name},
                        ))
                        ks.add_relationship(Relationship(
                            id=Relationship.make_id(cid, RelationKind.IMPLEMENTS, mid2),
                            source=cid, target=mid2, kind=RelationKind.IMPLEMENTS,
                            confidence=Confidence.KNOWN, evidence="method",
                        ))

    def _extract_imports(self, f: Path, rel: str, module_ids: dict[str, str], ks: KnowledgeSurface) -> None:
        try:
            tree = ast.parse(f.read_text(), filename=rel)
        except SyntaxError:
            return
        src_mid = module_ids.get(rel)
        if not src_mid:
            return
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    self._add_import_rel(src_mid, alias.name, module_ids, ks, rel)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    self._add_import_rel(src_mid, node.module, module_ids, ks, rel)

    def _add_import_rel(self, src_mid: str, modname: str, module_ids: dict[str, str], ks: KnowledgeSurface, rel: str) -> None:
        # Map dotted module name to a file if present (honest: only if found)
        target_mid = None
        for rpath, mid in module_ids.items():
            if rpath.replace("/", ".").replace(".py", "") == modname or rpath == modname + ".py":
                target_mid = mid
                break
        if target_mid is None:
            # External or unresolved import: record as unknown-confidence edge to a synthetic module
            target_mid = Entity.make_id(EntityKind.MODULE, f"<external:{modname}>")
            if ks.entity(target_mid) is None:
                ks.add_entity(Entity(
                    id=target_mid, kind=EntityKind.MODULE, name=f"<external:{modname}>",
                    confidence=Confidence.UNKNOWN,
                    provenance=Provenance(created_by="extractor:ast", source=rel, rationale="unresolved import"),
                    attributes={"external": True},
                ))
        try:
            ks.add_relationship(Relationship(
                id=Relationship.make_id(src_mid, RelationKind.IMPORTS, target_mid),
                source=src_mid, target=target_mid, kind=RelationKind.IMPORTS,
                confidence=Confidence.KNOWN if target_mid in module_ids.values() else Confidence.INFERRED,
                evidence=f"import {modname}",
            ))
        except KeyError:
            pass
