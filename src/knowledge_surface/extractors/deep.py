"""Deeper code understanding: call graph, dynamic imports, framework behavior.

These extractors add edges and capabilities that a file-only reader misses:
indirect calls, runtime imports, and framework entry points.
"""

from __future__ import annotations

import ast
from pathlib import Path

from ..representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    Provenance,
    RelationKind,
    Relationship,
)
from ..representation.knowledge_surface import KnowledgeSurface


def _call_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        parts = [f.attr]
        cur = f.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


class CallGraphExtractor:
    """Resolve calls between locally defined functions/classes."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        by_name: dict[str, list[Entity]] = {}
        for e in ks.entities():
            if e.kind in (EntityKind.FUNCTION, EntityKind.CLASS):
                by_name.setdefault(e.name.split(".")[-1], []).append(e)
        added = 0
        for f in root.rglob("*.py"):
            rel = str(f.relative_to(root))
            if "__pycache__" in rel:
                continue
            try:
                tree = ast.parse(f.read_text())
            except (SyntaxError, OSError):
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                    continue
                fname = fn.name
                owner = next(
                    (e for e in ks.entities() if e.location and e.location.file == rel and e.name.split(".")[-1] == fname),
                    None,
                )
                if owner is None:
                    continue
                for call in ast.walk(fn):
                    if not isinstance(call, ast.Call):
                        continue
                    target_name = _call_name(call).split(".")[-1]
                    targets = by_name.get(target_name, [])
                    for t in targets:
                        if t.id == owner.id:
                            continue
                        rid = Relationship.make_id(owner.id, RelationKind.CALLS, t.id)
                        if ks.has_relationship(rid):
                            continue
                        ks.add_relationship(Relationship(
                            id=rid, source=owner.id, target=t.id, kind=RelationKind.CALLS,
                            confidence=Confidence.INFERRED,
                            evidence=f"call to {target_name} at {rel}:{call.lineno}",
                            provenance=Provenance(created_by="extractor:callgraph", source=rel,
                                                  rationale="name-based resolution; may be ambiguous"),
                        ))
                        added += 1
        return added


class DynamicImportExtractor:
    """Detect importlib.import_module(...) and __import__(...) calls."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        modules = {e.name: e for e in ks.entities(EntityKind.MODULE)}
        added = 0
        for f in root.rglob("*.py"):
            rel = str(f.relative_to(root))
            if "__pycache__" in rel:
                continue
            try:
                tree = ast.parse(f.read_text())
            except (SyntaxError, OSError):
                continue
            src = next((e for e in ks.entities(EntityKind.MODULE)
                        if e.location and e.location.file == rel), None)
            if src is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                name = _call_name(node)
                if name not in ("importlib.import_module", "__import__"):
                    continue
                if not node.args:
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    target_name = str(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    # f-string import: record the static prefix, mark unresolved
                    prefix = "".join(
                        str(v.value) for v in arg.values if isinstance(v, ast.Constant)
                    )
                    target_name = f"{prefix}*"
                else:
                    continue
                target = modules.get(target_name) or modules.get(f"{target_name}.py")
                if target is None:
                    tid = Entity.make_id(EntityKind.MODULE, f"<dynamic:{target_name}>")
                    if ks.entity(tid) is None:
                        ks.add_entity(Entity(
                            id=tid, kind=EntityKind.MODULE, name=f"<dynamic:{target_name}>",
                            confidence=Confidence.INFERRED,
                            provenance=Provenance(created_by="extractor:dynamic", source=rel,
                                                  rationale="runtime import target not statically resolvable"),
                        ))
                    target = ks.entity(tid)
                rid = Relationship.make_id(src.id, RelationKind.IMPORTS, target.id)
                if ks.has_relationship(rid):
                    continue
                ks.add_relationship(Relationship(
                    id=rid, source=src.id, target=target.id, kind=RelationKind.IMPORTS,
                    confidence=Confidence.INFERRED,
                    evidence=f"dynamic import {target_name} at {rel}:{node.lineno}",
                    provenance=Provenance(created_by="extractor:dynamic", source=rel),
                ))
                added += 1
        return added


_FRAMEWORK_DECORATORS = {
    "route", "get", "post", "put", "delete", "patch", "api_view",
    "login_required", "permission_required", "task", "command",
}


class FrameworkExtractor:
    """Surface framework entry points and guards as capabilities."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        added = 0
        for f in root.rglob("*.py"):
            rel = str(f.relative_to(root))
            if "__pycache__" in rel:
                continue
            try:
                tree = ast.parse(f.read_text())
            except (SyntaxError, OSError):
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                for deco in fn.decorator_list:
                    dname = _call_name(deco) if isinstance(deco, ast.Call) else (
                        deco.id if isinstance(deco, ast.Name) else (
                            deco.attr if isinstance(deco, ast.Attribute) else ""))
                    leaf = dname.split(".")[-1]
                    if leaf not in _FRAMEWORK_DECORATORS:
                        continue
                    cap_id = Entity.make_id(EntityKind.CAPABILITY, f"framework:{leaf}")
                    if ks.entity(cap_id) is None:
                        ks.add_entity(Entity(
                            id=cap_id, kind=EntityKind.CAPABILITY, name=f"framework:{leaf}",
                            confidence=Confidence.INFERRED,
                            provenance=Provenance(created_by="extractor:framework", source=rel,
                                                  rationale=f"decorator {dname}"),
                        ))
                    fn_ent = next((e for e in ks.entities(EntityKind.FUNCTION)
                                   if e.location and e.location.file == rel
                                   and e.name.split(".")[-1] == fn.name), None)
                    if fn_ent is None:
                        continue
                    rid = Relationship.make_id(fn_ent.id, RelationKind.REQUIRES, cap_id)
                    if ks.has_relationship(rid):
                        continue
                    ks.add_relationship(Relationship(
                        id=rid, source=fn_ent.id, target=cap_id, kind=RelationKind.REQUIRES,
                        confidence=Confidence.INFERRED,
                        evidence=f"@{dname} at {rel}:{fn.lineno}",
                    ))
                    added += 1
        return added
