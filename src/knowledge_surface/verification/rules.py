"""Semantic invariant rules.

Every rule returns one of three outcomes: PASS, FAIL, or UNKNOWN. UNKNOWN is
never treated as PASS. The engine compares the before and after outcomes to
classify a change as introduced, pre-existing, improved, or indeterminate.

Rule semantics are deliberately narrow and documented:

* ``ForbiddenImportRule`` inspects import syntax only; it does not resolve
  re-exports or runtime module mutation.
* ``RequireCallRule`` inspects calls in the target function's own scope
  (nested functions/classes excluded) and uses a conservative block-dominance
  check for ordering. It does not model exceptions, aliases, or dynamic
  dispatch.
* ``ForbiddenCallRule`` inspects syntactic calls in matching files.
* ``BehavioralRule`` is executed by the engine only when explicitly trusted.
"""

from __future__ import annotations

import ast
import re
from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass, field
from enum import StrEnum

from ..representation.entities import Confidence
from ..representation.knowledge_surface import KnowledgeSurface
from .change import ChangeSet

_NESTED = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


class Outcome(StrEnum):
    PASS = "pass"
    FAIL = "fail"
    UNKNOWN = "unknown"


@dataclass
class RuleContext:
    before: KnowledgeSurface
    after: KnowledgeSurface
    changes: ChangeSet
    before_tree: dict[str, str] = field(default_factory=dict)
    after_tree: dict[str, str] = field(default_factory=dict)
    before_errors: dict[str, str] = field(default_factory=dict)
    after_errors: dict[str, str] = field(default_factory=dict)

    @property
    def changed_python_paths(self) -> set[str]:
        return {p for p in self.changes.touched_paths() if p.endswith(".py")}

    def relevant_error(self, pattern: re.Pattern[str] | None = None) -> str | None:
        """First parse error in a *changed* file, optionally scoped by path."""
        for path, error in sorted(self.after_errors.items()):
            if path not in self.changed_python_paths:
                continue
            if pattern is not None and not pattern.search(path):
                continue
            return error
        return None

    def after_asts(self) -> dict[str, ast.Module]:
        return _parsed(self.after_tree)

    def before_asts(self) -> dict[str, ast.Module]:
        return _parsed(self.before_tree)


@dataclass
class RuleResult:
    rule_id: str
    outcome: Outcome
    message: str
    confidence: Confidence = Confidence.KNOWN
    path: str = ""
    line: int = 0
    evidence: str = ""
    suggestion: str = ""
    missing_target: bool = False

    @property
    def passed(self) -> bool:
        return self.outcome is Outcome.PASS

    @classmethod
    def unknown(cls, rule_id: str, message: str, **kwargs) -> RuleResult:
        return cls(rule_id=rule_id, outcome=Outcome.UNKNOWN, message=message,
                   confidence=Confidence.UNKNOWN, **kwargs)


class Rule(ABC):
    id: str
    description: str
    severity: str = "error"

    @abstractmethod
    def evaluate(self, ctx: RuleContext) -> RuleResult:
        ...


def _parsed(tree: dict[str, str]) -> dict[str, ast.Module]:
    from .change import parse_python

    out: dict[str, ast.Module] = {}
    for path, source in tree.items():
        parsed, error = parse_python(source, path)
        if parsed is not None:
            out[path] = parsed
    return out


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


def _matches(name: str, target: str) -> bool:
    return name == target or name.endswith("." + target)


def _imports(tree: ast.Module) -> list[tuple[str, int]]:
    out: list[tuple[str, int]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                out.append((alias.name, node.lineno))
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * node.level + (node.module or "")
            for alias in node.names:
                out.append((f"{prefix}.{alias.name}" if prefix else alias.name, node.lineno))
                if prefix:
                    out.append((prefix, node.lineno))
    return out


def _funcs(tree: ast.Module) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    return [n for n in ast.walk(tree) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]


def _iter_functions(tree: ast.Module):
    """Yield ``(owner_class, function)`` pairs, including nested classes."""
    stack: list[tuple[str, ast.AST]] = [("", tree)]
    while stack:
        owner, node = stack.pop()
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                stack.append((child.name, child))
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield owner, child


def _calls_in_own_scope(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[tuple[str, int, ast.Call]]:
    """Calls in the function body, excluding nested functions/classes/lambdas."""
    out: list[tuple[str, int, ast.Call]] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, _NESTED) and node is not fn:
            return
        if isinstance(node, ast.Call):
            out.append((_call_name(node), node.lineno, node))
        for child in ast.iter_child_nodes(node):
            visit(child)

    for stmt in fn.body:
        visit(stmt)
    return out


def _direct_calls(stmt: ast.stmt) -> list[tuple[str, int, ast.Call]]:
    """Calls evaluated by *stmt* itself, not inside its nested control-flow bodies."""
    out: list[tuple[str, int, ast.Call]] = []

    def visit(node: ast.AST) -> None:
        if isinstance(node, ast.Call):
            out.append((_call_name(node), node.lineno, node))
        for field_name, value in ast.iter_fields(node):
            if field_name in ("body", "orelse", "finalbody", "handlers", "cases"):
                continue
            if isinstance(value, ast.AST):
                visit(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, ast.AST):
                        visit(item)

    visit(stmt)
    return out


def _parent_map(fn: ast.AST) -> dict[ast.AST, ast.AST]:
    parents: dict[ast.AST, ast.AST] = {}
    for node in ast.walk(fn):
        for child in ast.iter_child_nodes(node):
            parents[child] = node
    return parents


def _block_contains(parent: ast.AST, child: ast.AST) -> tuple[list[ast.stmt] | None, int]:
    for _, value in ast.iter_fields(parent):
        if isinstance(value, list) and child in value and all(
            isinstance(item, ast.stmt) for item in value
        ):
            return value, value.index(child)  # type: ignore[return-value]
    return None, -1


def _dominates(fn: ast.FunctionDef | ast.AsyncFunctionDef, required: str, protected: ast.Call) -> bool:
    """Conservative: required must be evaluated before protected on every path
    represented by the enclosing statement blocks we can see."""
    parents = _parent_map(fn)
    node: ast.AST = protected
    while node is not fn:
        parent = parents.get(node)
        if parent is None:
            break
        if isinstance(node, ast.stmt):
            block, idx = _block_contains(parent, node)
            if block is not None:
                for sibling in block[:idx]:
                    if any(_matches(name, required) for name, _, _ in _direct_calls(sibling)):
                        return True
            # A guard evaluated in the parent's condition dominates its body.
            if isinstance(parent, (ast.If, ast.While)) and node in parent.body:
                if any(_matches(name, required) for name, _, _ in _direct_calls(parent.test)):
                    return True
            if isinstance(parent, ast.With) and node in parent.body:
                for item in parent.items:
                    if any(_matches(name, required) for name, _, _ in _direct_calls(item.context_expr)):
                        return True
        node = parent
    return False


class ForbiddenImportRule(Rule):
    """A source module must not import a forbidden module/name."""

    def __init__(self, id: str, source: str, forbidden: str, description: str = ""):
        self.id = id
        self.source = re.compile(source)
        self.forbidden = re.compile(forbidden)
        self.description = description or f"{source} must not import {forbidden}"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        hits: list[str] = []
        first_path, first_line = "", 0
        for path, tree in sorted(asts.items()):
            if not self.source.search(path):
                continue
            for mod, line in _imports(tree):
                if self.forbidden.search(mod):
                    hits.append(f"{path}:{line} imports {mod}")
                    if not first_path:
                        first_path, first_line = path, line
        return (not hits, "; ".join(hits), first_path, first_line)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error(self.source)
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, outcome=Outcome.PASS if ok else Outcome.FAIL,
            message=self.description if not ok else "no forbidden import",
            path=path, line=line, evidence=ev,
            suggestion="Remove the forbidden import or route through an allowed boundary.",
        )


class RequireCallRule(Rule):
    """A matching function must call a required callee before a protected call.

    Missing targets fail by default. Set ``required=False`` for rules that
    intentionally apply only when the target exists.
    """

    def __init__(self, id: str, function: str, callee: str,
                 before_call: str | None = None, description: str = "",
                 owner: str | None = None, required: bool = True):
        self.id = id
        self.function = re.compile(function)
        self.callee = callee
        self.before_call = before_call
        self.owner = re.compile(owner) if owner else None
        self.description = description or f"{function} must call {callee}"
        self.required = required
        self.severity = "error"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[Outcome, str, str, int, bool]:
        checked = 0
        for path, tree in sorted(asts.items()):
            for cls, fn in _iter_functions(tree):
                if not self.function.search(fn.name):
                    continue
                if self.owner is not None and not self.owner.search(cls):
                    continue
                checked += 1
                calls = _calls_in_own_scope(fn)
                required = [c for c in calls if _matches(c[0], self.callee)]
                if not required:
                    return (Outcome.FAIL,
                            f"{path}:{fn.lineno} {fn.name} does not call {self.callee}",
                            path, fn.lineno, False)
                if self.before_call:
                    protected = [c for c in calls if _matches(c[0], self.before_call)]
                    if protected:
                        first = min(protected, key=lambda c: (c[1], c[2].col_offset))
                        if not _dominates(fn, self.callee, first[2]):
                            return (Outcome.FAIL,
                                    f"{path}:{fn.lineno} {self.callee} does not dominate "
                                    f"{self.before_call}",
                                    path, fn.lineno, False)
        if checked == 0:
            if self.required:
                return (Outcome.FAIL,
                        f"target function {self.function.pattern} not found",
                        "", 0, True)
            return (Outcome.PASS, "target absent (optional rule)", "", 0, False)
        return (Outcome.PASS, "", "", 0, False)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        outcome, ev, path, line, missing = self._check(ctx.after_asts())
        if outcome is Outcome.UNKNOWN:
            return RuleResult.unknown(self.id, ev or "indeterminate", path=path, line=line, evidence=ev)
        return RuleResult(
            rule_id=self.id, outcome=outcome,
            message=(ev or self.description) if outcome is Outcome.FAIL else "required call present",
            path=path, line=line, evidence=ev,
            suggestion=f"Call {self.callee} before the protected operation.",
            missing_target=missing,
        )


class ForbiddenCallRule(Rule):
    def __init__(self, id: str, scope: str, callee: str, description: str = ""):
        self.id = id
        self.scope = re.compile(scope)
        self.callee = callee
        self.description = description or f"{scope} must not call {callee}"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error(self.scope)
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        for path, tree in sorted(ctx.after_asts().items()):
            if not self.scope.search(path):
                continue
            for fn in _funcs(tree):
                for name, line, _ in _calls_in_own_scope(fn):
                    if _matches(name, self.callee):
                        return RuleResult(
                            rule_id=self.id, outcome=Outcome.FAIL,
                            message=f"{fn.name} calls forbidden {self.callee}",
                            path=path, line=line, evidence=f"{path}:{line} calls {name}",
                            suggestion=f"Remove the call to {self.callee}.",
                        )
            # Calls outside a function (module level).
            for name, line, _ in _module_level_calls(tree):
                if _matches(name, self.callee):
                    return RuleResult(
                        rule_id=self.id, outcome=Outcome.FAIL,
                        message=f"module calls forbidden {self.callee}",
                        path=path, line=line, evidence=f"{path}:{line} calls {name}",
                        suggestion=f"Remove the call to {self.callee}.",
                    )
        return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="ok")


def _module_level_calls(tree: ast.Module) -> list[tuple[str, int, ast.Call]]:
    out: list[tuple[str, int, ast.Call]] = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        for name, line, node in _direct_calls(stmt):
            out.append((name, line, node))
    return out


class NoOrphanedCallsRule(Rule):
    """Deleting a function is unsafe while another module still calls it.

    Names are compared across the whole tree, so a pure file rename does not
    count as a deletion.
    """

    def __init__(self, id: str = "no-orphaned-calls"):
        self.id = id
        self.description = "deleted functions must not leave call sites behind"

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        before_names = {fn.name for tree in ctx.before_asts().values() for fn in _funcs(tree)}
        after_names = {fn.name for tree in ctx.after_asts().values() for fn in _funcs(tree)}
        deleted = {name for name in before_names - after_names if not name.startswith("__")}
        if not deleted:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS,
                              message="no deleted functions")
        for path, tree in sorted(ctx.after_asts().items()):
            for fn in _funcs(tree):
                for name, line, _ in _calls_in_own_scope(fn):
                    leaf = name.split(".")[-1]
                    if leaf in deleted:
                        return RuleResult(
                            rule_id=self.id, outcome=Outcome.FAIL,
                            message=f"{fn.name} still calls deleted function {leaf}",
                            path=path, line=line,
                            evidence=f"{path}:{line} calls {name}",
                            suggestion=f"Update {path}:{line} or keep {leaf}.",
                        )
            for name, line, _ in _module_level_calls(tree):
                leaf = name.split(".")[-1]
                if leaf in deleted:
                    return RuleResult(
                        rule_id=self.id, outcome=Outcome.FAIL,
                        message=f"module still calls deleted function {leaf}",
                        path=path, line=line,
                        evidence=f"{path}:{line} calls {name}",
                        suggestion=f"Update {path}:{line} or keep {leaf}.",
                    )
        return RuleResult(rule_id=self.id, outcome=Outcome.PASS,
                          message="no orphaned callers")


class TypeAnnotationRule(Rule):
    """Public functions must be fully annotated (structural invariant)."""

    def __init__(self, id: str, skip_private: bool = True):
        self.id = id
        self.skip_private = skip_private
        self.description = "public functions must be fully annotated"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        for path, tree in sorted(asts.items()):
            for fn in _funcs(tree):
                if self.skip_private and fn.name.startswith("_"):
                    continue
                args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
                missing = [a.arg for a in args if a.annotation is None and a.arg not in ("self", "cls")]
                if fn.returns is None or missing:
                    return (False, f"{path}:{fn.lineno} {fn.name} missing annotations", path, fn.lineno)
        return (True, "", "", 0)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, outcome=Outcome.PASS if ok else Outcome.FAIL,
            message=self.description if not ok else "annotated",
            path=path, line=line, evidence=ev,
            suggestion="Add parameter and return type annotations.",
        )


class NoMutableDefaultRule(Rule):
    def __init__(self, id: str = "no-mutable-default"):
        self.id = id
        self.description = "functions must not use mutable default arguments"

    def _check(self, asts: dict[str, ast.Module]) -> tuple[bool, str, str, int]:
        for path, tree in sorted(asts.items()):
            for fn in _funcs(tree):
                defaults = list(fn.args.defaults) + [d for d in fn.args.kw_defaults if d is not None]
                for default in defaults:
                    if isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        return (False, f"{path}:{fn.lineno} {fn.name} mutable default", path, fn.lineno)
        return (True, "", "", 0)

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        ok, ev, path, line = self._check(ctx.after_asts())
        return RuleResult(
            rule_id=self.id, outcome=Outcome.PASS if ok else Outcome.FAIL,
            message=self.description if not ok else "ok",
            path=path, line=line, evidence=ev,
            suggestion="Use None as the default and create the container inside the function.",
        )


class RequiredDecoratorRule(Rule):
    def __init__(self, id: str, function: str, decorator: str,
                 description: str = "", required: bool = True):
        self.id = id
        self.function = re.compile(function)
        self.decorator = decorator
        self.description = description or f"{function} must be decorated with {decorator}"
        self.required = required

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        checked = 0
        for path, tree in sorted(ctx.after_asts().items()):
            for fn in _funcs(tree):
                if not self.function.search(fn.name):
                    continue
                checked += 1
                decos = []
                for deco in fn.decorator_list:
                    if isinstance(deco, ast.Call):
                        decos.append(_call_name(deco))
                    elif isinstance(deco, ast.Name):
                        decos.append(deco.id)
                    elif isinstance(deco, ast.Attribute):
                        decos.append(deco.attr)
                if not any(_matches(d, self.decorator) for d in decos):
                    return RuleResult(
                        rule_id=self.id, outcome=Outcome.FAIL,
                        message=f"{fn.name} missing @{self.decorator}",
                        path=path, line=fn.lineno,
                        evidence=f"{path}:{fn.lineno} decorators={decos}",
                        suggestion=f"Add @{self.decorator} to {fn.name}.",
                    )
        if checked == 0 and self.required:
            return RuleResult(
                rule_id=self.id, outcome=Outcome.FAIL,
                message=f"target function {self.function.pattern} not found",
                suggestion="Add the function or set required=false for an optional rule.",
                missing_target=True,
            )
        return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="ok")


class CustomRule(Rule):
    """Escape hatch: a predicate over the RuleContext."""

    def __init__(self, id: str, predicate: Callable[[RuleContext], RuleResult], description: str = ""):
        self.id = id
        self.predicate = predicate
        self.description = description or id

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        return self.predicate(ctx)


class BehavioralRule(Rule):
    """Run a Python snippet against the candidate tree.

    The engine executes this only if ``trusted`` is true or the verifier was
    constructed with ``allow_untrusted_behavioral=True``. The snippet must
    define ``check()`` and raise on violation.
    """

    def __init__(self, id: str, snippet: str, description: str = "", trusted: bool = False):
        self.id = id
        self.snippet = snippet
        self.description = description or id
        self.trusted = trusted

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        return RuleResult.unknown(
            self.id, "behavioural rule is executed by the engine", confidence=Confidence.UNKNOWN,
        )


class Allowlist:
    """Suppress specific rule/path pairs while preserving the reason."""

    def __init__(self, entries: list[tuple[str, ...]] | None = None):
        self.entries: list[tuple[str, str, str]] = []
        for entry in entries or []:
            if len(entry) == 2:
                self.entries.append((entry[0], entry[1], "allowlisted"))
            elif len(entry) == 3:
                self.entries.append((entry[0], entry[1], entry[2]))
            else:
                raise ValueError(f"allowlist entry must have 2 or 3 values: {entry!r}")

    def reason(self, rule_id: str, path: str) -> str | None:
        for rule, rule_path, reason in self.entries:
            if rule in ("*", rule_id) and rule_path in ("*", path):
                return reason
        return None

    def allows(self, rule_id: str, path: str) -> bool:
        return self.reason(rule_id, path) is not None
