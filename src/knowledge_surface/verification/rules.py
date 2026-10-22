"""Semantic invariant rules.

A rule evaluates the *after* state and compares it with the *before* state.
A change is a violation only when it introduces a failure (pass -> fail) or
adds a new failing file. Pre-existing debt is reported but never blocks a
change. This is the core of false-positive control.
"""

from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field

from ..representation.entities import Confidence
from ..representation.knowledge_surface import KnowledgeSurface
from .change import ChangeSet, parse


@dataclass
class RuleContext:
    before: KnowledgeSurface
    after: KnowledgeSurface
    changes: ChangeSet
    before_tree: dict[str, str] = field(default_factory=dict)
    after_tree: dict[str, str] = field(default_factory=dict)

    def after_asts(self) -> dict[str, ast.Module]:
        return {p: t for p, s in self.after_tree.items() if (t := parse(s)) is not None}

    def before_asts(self) -> dict[str, ast.Module]:
        return {p: t for p, s in self.before_tree.items() if (t := parse(s)) is not None}


@dataclass
class RuleResult:
    rule_id: str
    passed: bool
    message: str
    confidence: Confidence = Confidence.KNOWN
    path: str = ""
    line: int = 0
    evidence: str = ""
    suggestion: str = ""


class Rule(ABC):
    id: str
    description: str
    severity: str = "error"

    @abstractmethod
    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ...


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


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                out.append((a.name, node.lineno))
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                out.append((f"{node.module}.{a.name}", node.lineno))
                out.append((node.module, node.lineno))
    return out


def _funcs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _iter_functions(tree: ast.Module):
    """Yield (owner_class, function) pairs, including nested class methods."""
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        owner, node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                stack.append((child.name, child))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield owner, child


def _calls_in(node: ast.AST) -> list[tuple[str, int]]:
    out = []
    for n in ast.walk(node):
        if isinstance(n, ast.Call):
            out.append((_call_name(n), n.lineno))
    return out


class ForbiddenImportRule(Rule):
    """A source module must not import a forbidden module/name."""

    def __init__(self, id: str, source: str, forbidden: str, description: str = ""):
        self.id = id
        self.source = re.compile(source)
        self.forbidden = re.compile(forbidden)
        self.description = description or f"{source} must not import {forbidden}"

    def _check(self, ctx: RuleContext, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        hits: list[str] = []
        first_path, first_line = "", 0
        for path, tree in asts.items():
            if not self.source.search(path):
                continue
            for mod, line in _imports(tree):
                if self.forbidden.search(mod):
                    hits.append(f"{path}:{line} imports {mod}")
                    if not first_path:
                        first_path, first_line = path, line
        return (not hits, "; ".join(hits), first_path, first_line)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ok, ev, path, line = self._check(ctx, ctx.after_asts())
        return RuleResult(
            rule_id=self.id, passed=ok,
            message=self.description if not ok else "no forbidden import",
            path=path, line=line, evidence=ev,
            suggestion="Remove the forbidden import or route through an allowed boundary.",
        )


class LayerRule(ForbiddenImportRule):
    """Generalized layer rule: a layer's modules must not import another layer."""


class RequireCallRule(Rule):
    """A matching function must call a required callee.

    If `before_call` is given, the required call must appear before that call.
    """

    def __init__(self, id: str, function: str, callee: str,
                 before_call: str | None = None, description: str = "",
                 owner: str | None = None):
        self.id = id
        self.function = re.compile(function)
        self.callee = callee
        self.before_call = before_call
        self.owner = re.compile(owner) if owner else None
        self.description = description or f"{function} must call {callee}"
        self.severity = "error"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        checked = 0
        for path, tree in asts.items():
            for cls, fn in _iter_functions(tree):
                if not self.function.search(fn.name):
                    continue
                if self.owner is not None and not self.owner.search(cls):
                    continue
                checked += 1
                calls = _calls_in(fn)
                names = [c[0] for c in calls]
                callee_ok = any(n == self.callee or n.endswith("." + self.callee) for n in names)
                if not callee_ok:
                    return (False, f"{path}:{fn.lineno} {fn.name} does not call {self.callee}",
                            path, fn.lineno)
                if self.before_call:
                    callee_line = min((ln for n, ln in calls if n == self.callee or n.endswith("." + self.callee)), default=0)
                    other_lines = [ln for n, ln in calls if n == self.before_call or n.endswith("." + self.before_call)]
                    if other_lines and callee_line > min(other_lines):
                        return (False, f"{path}:{fn.lineno} {self.callee} called after {self.before_call}",
                                path, fn.lineno)
        if checked == 0:
            return (True, "no matching functions", "", 0)
        return (True, "", "", 0)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, passed=ok,
            message=self.description if not ok else "required call present",
            path=path, line=line, evidence=ev,
            suggestion=f"Call {self.callee} before the protected operation.",
        )


class ForbiddenCallRule(Rule):
    def __init__(self, id: str, scope: str, callee: str, description: str = ""):
        self.id = id
        self.scope = re.compile(scope)
        self.callee = callee
        self.description = description or f"{scope} must not call {callee}"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        for path, tree in ctx.after_asts().items():
            if not self.scope.search(path):
                continue
            for fn in _funcs(tree):
                for name, line in _calls_in(fn):
                    if name == self.callee or name.endswith("." + self.callee):
                        return RuleResult(
                            rule_id=self.id, passed=False,
                            message=f"{fn.name} calls forbidden {self.callee}",
                            path=path, line=line,
                            evidence=f"{path}:{line}",
                            suggestion=f"Remove the call to {self.callee}.",
                        )
        return RuleResult(rule_id=self.id, passed=True, message="ok")


class NoOrphanedCallsRule(Rule):
    """Deleting a function is unsafe while another module still calls it.

    This is a cross-file effect: the call site can live in a file the change
    never touched, which is exactly what file-local reasoning misses.
    """

    def __init__(self, id: str = "no-orphaned-calls"):
        self.id = id
        self.description = "deleted functions must not leave call sites behind"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        before_funcs = {(p, fn.name) for p, t in ctx.before_asts().items() for fn in _funcs(t)}
        after_funcs = {(p, fn.name) for p, t in ctx.after_asts().items() for fn in _funcs(t)}
        deleted = {name for (p, name) in before_funcs if (p, name) not in after_funcs and name != "__init__"}
        if not deleted:
            return RuleResult(rule_id=self.id, passed=True, message="no deleted functions")
        for path, tree in ctx.after_asts().items():
            for fn in _funcs(tree):
                for name, line in _calls_in(fn):
                    leaf = name.split(".")[-1]
                    if leaf in deleted:
                        return RuleResult(
                            rule_id=self.id, passed=False,
                            message=f"{fn.name} still calls deleted function {leaf}",
                            path=path, line=line,
                            evidence=f"{path}:{line} calls {name}",
                            suggestion=f"Update {path}:{line} or keep {leaf}.",
                        )
        return RuleResult(rule_id=self.id, passed=True, message="no orphaned callers")


class TypeAnnotationRule(Rule):
    """Public functions must be fully annotated (structural invariant)."""

    def __init__(self, id: str, skip_private: bool = True):
        self.id = id
        self.skip_private = skip_private
        self.description = "public functions must be fully annotated"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        for path, tree in asts.items():
            for fn in _funcs(tree):
                if self.skip_private and fn.name.startswith("_"):
                    continue
                missing = [a.arg for a in fn.args.args if a.annotation is None and a.arg not in ("self", "cls")]
                if fn.returns is None or missing:
                    return (False, f"{path}:{fn.lineno} {fn.name} missing annotations", path, fn.lineno)
        return (True, "", "", 0)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, passed=ok, message=self.description if not ok else "annotated",
            path=path, line=line, evidence=ev,
            suggestion="Add parameter and return type annotations.",
        )


class NoMutableDefaultRule(Rule):
    def __init__(self, id: str = "no-mutable-default"):
        self.id = id
        self.description = "functions must not use mutable default arguments"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        for path, tree in asts.items():
            for fn in _funcs(tree):
                for default in list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        return (False, f"{path}:{fn.lineno} {fn.name} mutable default", path, fn.lineno)
        return (True, "", "", 0)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, passed=ok, message=self.description if not ok else "ok",
            path=path, line=line, evidence=ev,
            suggestion="Use None as the default and create the container inside the function.",
        )


class RequiredDecoratorRule(Rule):
    def __init__(self, id: str, function: str, decorator: str, description: str = ""):
        self.id = id
        self.function = re.compile(function)
        self.decorator = decorator
        self.description = description or f"{function} must be decorated with {decorator}"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        for path, tree in ctx.after_asts().items():
            for fn in _funcs(tree):
                if not self.function.search(fn.name):
                    continue
                decos = []
                for d in fn.decorator_list:
                    decos.append(_call_name(d) if isinstance(d, ast.Call) else (d.id if isinstance(d, ast.Name) else (d.attr if isinstance(d, ast.Attribute) else "")))
                if not any(d == self.decorator or d.endswith("." + self.decorator) for d in decos):
                    return RuleResult(
                        rule_id=self.id, passed=False,
                        message=f"{fn.name} missing @{self.decorator}",
                        path=path, line=fn.lineno,
                        evidence=f"{path}:{fn.lineno}",
                        suggestion=f"Add @{self.decorator} to {fn.name}.",
                    )
        return RuleResult(rule_id=self.id, passed=True, message="ok")


class CustomRule(Rule):
    """Escape hatch: a predicate over the RuleContext."""

    def __init__(self, id: str, predicate: Callable[[RuleContext], RuleResult], description: str = ""):
        self.id = id
        self.predicate = predicate
        self.description = description or id

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        return self.predicate(ctx)


class BehavioralRule(Rule):
    """Run a Python test function against the post-change tree.

    The snippet must define ``check()`` and raise AssertionError on violation.
    Execution is isolated by the caller (see engine) and bounded by timeout.
    """

    def __init__(self, id: str, snippet: str, description: str = ""):
        self.id = id
        self.snippet = snippet
        self.description = description or id

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        # Evaluation is performed by the engine (needs subprocess + tree write).
        return RuleResult(rule_id=self.id, passed=True, message="deferred")


class Allowlist:
    """Suppress specific rule/path pairs, the way linters do."""

    def __init__(self, entries: list[tuple[str, str]] | None = None):
        self.entries = entries or []

    def allows(self, rule_id: str, path: str) -> bool:
        return any(r in ("*", rule_id) and (p in ("*", path)) for r, p in self.entries)
