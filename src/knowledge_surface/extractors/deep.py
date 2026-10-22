"""Deeper code understanding: call graph, dynamic imports, framework behavior.

These extractors add edges that a file-only reader misses: indirect calls,
runtime imports, and framework entry points.

Every edge here is *inferred*, not proven at runtime. Name resolution is
deliberately conservative: when a call could target more than one local
definition, the edge is skipped and counted as ambiguous instead of guessing.
"""

from __future__ import annotations

import ast
from pathlib import Path, PurePosixPath

from ..paths import iter_python_files
from ..representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    Provenance,
    RelationKind,
    Relationship,
)
from ..representation.knowledge_surface import KnowledgeSurface

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


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


def _own_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[ast.Call]:
    """Calls in this function, excluding nested functions/classes/lambdas."""
    out: list[ast.Call] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, _NESTED) and node is not fn:
            return
        if isinstance(node, ast.Call):
            out.append(node)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in fn.body:
        visit(stmt)
    return out


def _local_names(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> set[str]:
    """Names bound in this function's own scope (arguments, assignments, defs)."""
    names = {
        a.arg for a in
        (*fn.args.posonlyargs, *fn.args.args, *fn.args.kwonlyargs)
    }
    if fn.args.vararg:
        names.add(fn.args.vararg.arg)
    if fn.args.kwarg:
        names.add(fn.args.kwarg.arg)
    def visit(node: ast.AST) -> None:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
            return
        if isinstance(node, ast.Lambda):
            return
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
            names.add(node.id)
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in fn.body:
        visit(stmt)
    return names


def _dotted(rel: str) -> str:
    parts = list(PurePosixPath(rel).parts)
    if parts and parts[-1].endswith(".py"):
        parts[-1] = parts[-1][:-3]
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _diagnostics(ks: KnowledgeSurface, key: str) -> dict:
    if not isinstance(ks.diagnostics.get(key), dict):
        ks.diagnostics[key] = {}
    return ks.diagnostics[key]


class CallGraphExtractor:
    """Resolve calls between locally defined functions."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        by_line = {
            (e.location.file, e.location.start_line): e
            for e in ks.entities()
            if e.kind == EntityKind.FUNCTION and e.location
        }
        by_leaf: dict[str, list[Entity]] = {}
        for e in ks.entities():
            if e.kind in (EntityKind.FUNCTION, EntityKind.CLASS):
                by_leaf.setdefault(e.name.split(".")[-1], []).append(e)

        added = 0
        ambiguous = 0
        for rel, full in iter_python_files(root):
            try:
                tree = ast.parse(full.read_text(encoding="utf-8"), filename=rel)
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            for fn in ast.walk(tree):
                if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                owner = by_line.get((rel, fn.lineno))
                if owner is None:
                    continue
                local = _local_names(fn)
                for call in _own_calls(fn):
                    leaf = _call_name(call).split(".")[-1]
                    if not leaf or leaf in local:
                        continue
                    targets = [t for t in by_leaf.get(leaf, []) if t.id != owner.id]
                    if len(targets) != 1:
                        if len(targets) > 1:
                            ambiguous += 1
                        continue
                    target = targets[0]
                    rid = Relationship.make_id(owner.id, RelationKind.CALLS, target.id)
                    if ks.has_relationship(rid):
                        continue
                    ks.add_relationship(Relationship(
                        id=rid, source=owner.id, target=target.id, kind=RelationKind.CALLS,
                        confidence=Confidence.INFERRED,
                        evidence=f"call to {leaf} at {rel}:{call.lineno}",
                        provenance=Provenance(
                            created_by="extractor:callgraph", source=rel,
                            rationale="name-based resolution; dynamic dispatch not modeled",
                        ),
                    ))
                    added += 1
        diag = _diagnostics(ks, "call_graph")
        diag.update({"edges_added": added, "ambiguous_calls_skipped": ambiguous})
        return added


class DynamicImportExtractor:
    """Detect importlib.import_module(...) and __import__(...) calls."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        modules = {}
        for e in ks.entities(EntityKind.MODULE):
            if e.location and e.location.file:
                modules[e.location.file] = e
                modules[_dotted(e.location.file)] = e
        for e in ks.entities(EntityKind.MODULE):
            modules.setdefault(e.name, e)

        added = 0
        unresolved = 0
        for rel, full in iter_python_files(root):
            try:
                tree = ast.parse(full.read_text(encoding="utf-8"), filename=rel)
            except (SyntaxError, OSError, UnicodeDecodeError):
                continue
            src = modules.get(rel) or modules.get(_dotted(rel))
            if src is None:
                continue
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                if _call_name(node) not in ("importlib.import_module", "__import__"):
                    continue
                if not node.args:
                    continue
                arg = node.args[0]
                if isinstance(arg, ast.Constant):
                    target_name = str(arg.value)
                elif isinstance(arg, ast.JoinedStr):
                    prefix = "".join(
                        str(v.value) for v in arg.values if isinstance(v, ast.Constant)
                    )
                    target_name = f"{prefix}*"
                else:
                    continue
                target = modules.get(target_name) or modules.get(f"{target_name}.py")
                if target is None:
                    unresolved += 1
                    tid = Entity.make_id(EntityKind.MODULE, f"<dynamic:{target_name}>")
                    target = ks.entity(tid)
                    if target is None:
                        target = ks.add_entity(Entity(
                            id=tid, kind=EntityKind.MODULE, name=f"<dynamic:{target_name}>",
                            confidence=Confidence.UNKNOWN,
                            provenance=Provenance(
                                created_by="extractor:dynamic", source=rel,
                                rationale="runtime import target not statically resolvable",
                            ),
                        ))
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
        diag = _diagnostics(ks, "dynamic_imports")
        diag.update({"edges_added": added, "unresolved_targets": unresolved})
        return added


_FRAMEWORK_DECORATORS = {
    "route", "get", "post", "put", "delete", "patch", "api_view",
    "login_required", "permission_required", "task", "command",
}


class FrameworkExtractor:
    """Surface framework entry points and guards as capabilities."""

    def enrich(self, ks: KnowledgeSurface, root: str | Path) -> int:
        root = Path(root)
        by_line = {
            (e.location.file, e.location.start_line): e
            for e in ks.entities(EntityKind.FUNCTION) if e.location
        }
        added = 0
        for rel, full in iter_python_files(root):
            try:
                tree = ast.parse(full.read_text(encoding="utf-8"), filename=rel)
            except (SyntaxError, OSError, UnicodeDecodeError):
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
                    fn_ent = by_line.get((rel, fn.lineno))
                    if fn_ent is None:
                        continue
                    cap_id = Entity.make_id(EntityKind.CAPABILITY, f"framework:{leaf}")
                    if ks.entity(cap_id) is None:
                        ks.add_entity(Entity(
                            id=cap_id, kind=EntityKind.CAPABILITY, name=f"framework:{leaf}",
                            confidence=Confidence.INFERRED,
                            provenance=Provenance(
                                created_by="extractor:framework", source=rel,
                                rationale=f"decorator {dname}",
                            ),
                        ))
                    rid = Relationship.make_id(fn_ent.id, RelationKind.REQUIRES, cap_id)
                    if ks.has_relationship(rid):
                        continue
                    ks.add_relationship(Relationship(
                        id=rid, source=fn_ent.id, target=cap_id, kind=RelationKind.REQUIRES,
                        confidence=Confidence.INFERRED,
                        evidence=f"@{dname} at {rel}:{fn.lineno}",
                    ))
                    added += 1
        _diagnostics(ks, "frameworks")["edges_added"] = added
        return added
