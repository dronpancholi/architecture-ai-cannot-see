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

    def relevant_error(self, pattern: re.Pattern[str] | None = None,
                       paths: set[str] | None = None) -> str | None:
        """First parse error that prevents evaluating *this rule's* scope.

        A parse error in a file outside the rule's scope does not invalidate
        the rule's evidence. Errors are not restricted to changed files: a
        pre-existing syntax error inside the scope still means the rule cannot
        see that file.
        """
        for path, error in sorted(self.after_errors.items()):
            if pattern is not None and not pattern.search(path):
                continue
            if paths is not None and path not in paths:
                continue
            return error
        return None

    def after_asts(self) -> dict[str, ast.Module]:
        return _parsed(self.after_tree)

    def before_asts(self) -> dict[str, ast.Module]:
        return _parsed(self.before_tree)


@dataclass(frozen=True)
class Violation:
    """One independently comparable rule violation.

    ``key`` identifies the violated semantic target without a line number or
    path, so an edit that only shifts lines does not create a new finding. The
    engine combines it with the (rename-canonicalized) path.
    """

    key: str
    path: str = ""
    line: int = 0
    message: str = ""
    evidence: str = ""
    suggestion: str = ""
    missing_target: bool = False


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
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.outcome is Outcome.PASS

    def evidence_items(self) -> list[Violation]:
        """Every comparable violation, including a legacy single-result rule."""
        if self.violations:
            return list(self.violations)
        if self.outcome is not Outcome.FAIL:
            return []
        key = "missing-target" if self.missing_target else f"legacy::{self.message}"
        return [Violation(
            key=key, path=self.path, line=self.line, message=self.message,
            evidence=self.evidence, suggestion=self.suggestion,
            missing_target=self.missing_target,
        )]

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
    """Yield ``(owner_class, function)`` for every function, including nested defs.

    A nested function is evaluated as its own call scope; its calls are not
    attributed to the enclosing function.
    """

    def walk(node: ast.AST, owner: str):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.ClassDef):
                yield from walk(child, child.name)
            elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                yield owner, child
                yield from walk(child, owner)
            else:
                yield from walk(child, owner)

    yield from walk(tree, "")


def _function_entries(tree: ast.Module):
    """Yield ``(owner, function, occurrence)`` with a stable duplicate index.

    ``occurrence`` disambiguates two same-name definitions in the same owner
    scope without using the line number. Definitions are ordered by source
    position; adding lines above them does not change the index.
    """
    entries = list(_iter_functions(tree))
    entries.sort(key=lambda item: (item[1].lineno, item[0], item[1].name))
    counts: dict[tuple[str, str], int] = {}
    for owner, fn in entries:
        bucket = (owner, fn.name)
        occurrence = counts.get(bucket, 0)
        counts[bucket] = occurrence + 1
        yield owner, fn, occurrence


def _function_key(owner: str, fn: ast.FunctionDef | ast.AsyncFunctionDef,
                  occurrence: int) -> str:
    return f"fn::{owner}::{fn.name}#{occurrence}"


def _occurrence_key(base: str, counts: dict[str, int]) -> str:
    """Keep the first key stable and suffix later duplicate targets."""
    occurrence = counts.get(base, 0)
    counts[base] = occurrence + 1
    return base if occurrence == 0 else f"{base}#{occurrence}"


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

    def _check(self, asts: dict[str, ast.Module]) -> list[Violation]:
        found: dict[tuple[str, str], Violation] = {}
        for path, tree in sorted(asts.items()):
            if not self.source.search(path):
                continue
            counts: dict[str, int] = {}
            for mod, line in _imports(tree):
                if not self.forbidden.search(mod):
                    continue
                key = _occurrence_key(f"import::{mod}", counts)
                if (path, key) not in found:
                    found[(path, key)] = Violation(
                        key=key, path=path, line=line,
                        message=self.description,
                        evidence=f"{path}:{line} imports {mod}",
                        suggestion=(
                            "Remove the forbidden import or route through an "
                            "allowed boundary."
                        ),
                    )
        return list(found.values())

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error(self.source)
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        violations = self._check(ctx.after_asts())
        if not violations:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS,
                              message="no forbidden import")
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion, violations=violations,
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

    def _check(self, asts: dict[str, ast.Module]) -> tuple[list[Violation], bool]:
        violations: list[Violation] = []
        checked = 0
        for path, tree in sorted(asts.items()):
            for owner, fn, occurrence in _function_entries(tree):
                if not self.function.search(fn.name):
                    continue
                if self.owner is not None and not self.owner.search(owner):
                    continue
                checked += 1
                key = _function_key(owner, fn, occurrence)
                calls = _calls_in_own_scope(fn)
                required = [c for c in calls if _matches(c[0], self.callee)]
                if not required:
                    violations.append(Violation(
                        key=f"require::{key}::{self.callee}",
                        path=path, line=fn.lineno,
                        message=f"{path}:{fn.lineno} {fn.name} does not call {self.callee}",
                        evidence=f"{path}:{fn.lineno} {fn.name} does not call {self.callee}",
                        suggestion=f"Call {self.callee} before the protected operation.",
                    ))
                    continue
                if self.before_call:
                    protected = [c for c in calls if _matches(c[0], self.before_call)]
                    if protected:
                        first = min(protected, key=lambda c: (c[1], c[2].col_offset))
                        if not _dominates(fn, self.callee, first[2]):
                            violations.append(Violation(
                                key=f"require::{key}::{self.callee}",
                                path=path, line=fn.lineno,
                                message=(
                                    f"{path}:{fn.lineno} {self.callee} does not dominate "
                                    f"{self.before_call}"
                                ),
                                evidence=(
                                    f"{path}:{fn.lineno} {self.callee} does not dominate "
                                    f"{self.before_call}"
                                ),
                                suggestion=(
                                    f"Call {self.callee} before the protected operation."
                                ),
                            ))
        if checked == 0 and self.required:
            violations.append(Violation(
                key="missing-target", path="", line=0,
                message=f"target function {self.function.pattern} not found",
                evidence=f"target function {self.function.pattern} not found",
                suggestion="Add the function or set required=false for an optional rule.",
                missing_target=True,
            ))
        return violations, checked == 0

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        violations, missing = self._check(ctx.after_asts())
        if not violations:
            return RuleResult(
                rule_id=self.id, outcome=Outcome.PASS,
                message="target absent (optional rule)" if missing else "required call present",
                missing_target=missing,
            )
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL,
            message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion,
            missing_target=missing,
            violations=violations,
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
        found: dict[tuple[str, str], Violation] = {}
        for path, tree in sorted(ctx.after_asts().items()):
            if not self.scope.search(path):
                continue
            counts: dict[str, int] = {}
            for owner, fn, occurrence in _function_entries(tree):
                for name, line, _ in _calls_in_own_scope(fn):
                    if not _matches(name, self.callee):
                        continue
                    base = f"call::{_function_key(owner, fn, occurrence)}::{self.callee}"
                    key = _occurrence_key(base, counts)
                    found.setdefault((path, key), Violation(
                        key=key, path=path, line=line,
                        message=f"{fn.name} calls forbidden {self.callee}",
                        evidence=f"{path}:{line} calls {name}",
                        suggestion=f"Remove the call to {self.callee}.",
                    ))
            # Calls outside a function (module level).
            for name, line, _ in _module_level_calls(tree):
                if not _matches(name, self.callee):
                    continue
                key = _occurrence_key(f"call::module::{self.callee}", counts)
                found.setdefault((path, key), Violation(
                    key=key, path=path, line=line,
                    message=f"module calls forbidden {self.callee}",
                    evidence=f"{path}:{line} calls {name}",
                    suggestion=f"Remove the call to {self.callee}.",
                ))
        if not found:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="ok")
        violations = list(found.values())
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion, violations=violations,
        )


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
        found: dict[tuple[str, str], Violation] = {}
        for path, tree in sorted(ctx.after_asts().items()):
            counts: dict[str, int] = {}
            for owner, fn, occurrence in _function_entries(tree):
                for name, line, _ in _calls_in_own_scope(fn):
                    leaf = name.split(".")[-1]
                    if leaf not in deleted:
                        continue
                    base = f"orphan::{_function_key(owner, fn, occurrence)}::{leaf}"
                    key = _occurrence_key(base, counts)
                    found.setdefault((path, key), Violation(
                        key=key, path=path, line=line,
                        message=f"{fn.name} still calls deleted function {leaf}",
                        evidence=f"{path}:{line} calls {name}",
                        suggestion=f"Update {path}:{line} or keep {leaf}.",
                    ))
            for name, line, _ in _module_level_calls(tree):
                leaf = name.split(".")[-1]
                if leaf not in deleted:
                    continue
                key = _occurrence_key(f"orphan::module::{leaf}", counts)
                found.setdefault((path, key), Violation(
                    key=key, path=path, line=line,
                    message=f"module still calls deleted function {leaf}",
                    evidence=f"{path}:{line} calls {name}",
                    suggestion=f"Update {path}:{line} or keep {leaf}.",
                ))
        if not found:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS,
                              message="no orphaned callers")
        violations = list(found.values())
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion, violations=violations,
        )


class TypeAnnotationRule(Rule):
    """Public functions must be fully annotated (structural invariant)."""

    def __init__(self, id: str, skip_private: bool = True):
        self.id = id
        self.skip_private = skip_private
        self.description = "public functions must be fully annotated"

    def _check(self, asts: dict[str, ast.Module]) -> list[Violation]:
        found: list[Violation] = []
        for path, tree in sorted(asts.items()):
            for owner, fn, occurrence in _function_entries(tree):
                if self.skip_private and fn.name.startswith("_"):
                    continue
                args = fn.args.posonlyargs + fn.args.args + fn.args.kwonlyargs
                missing = [
                    a.arg for a in args
                    if a.annotation is None and a.arg not in ("self", "cls")
                ]
                if fn.returns is None or missing:
                    found.append(Violation(
                        key=f"annotation::{_function_key(owner, fn, occurrence)}",
                        path=path, line=fn.lineno,
                        message=f"{path}:{fn.lineno} {fn.name} missing annotations",
                        evidence=(
                            f"{path}:{fn.lineno} {fn.name} missing return={fn.returns is None} "
                            f"args={missing}"
                        ),
                        suggestion="Add parameter and return type annotations.",
                    ))
        return found

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        violations = self._check(ctx.after_asts())
        if not violations:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="annotated")
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion, violations=violations,
        )


class NoMutableDefaultRule(Rule):
    def __init__(self, id: str = "no-mutable-default"):
        self.id = id
        self.description = "functions must not use mutable default arguments"

    def _check(self, asts: dict[str, ast.Module]) -> list[Violation]:
        found: list[Violation] = []
        for path, tree in sorted(asts.items()):
            for owner, fn, occurrence in _function_entries(tree):
                key = _function_key(owner, fn, occurrence)
                positional = fn.args.posonlyargs + fn.args.args
                offset = len(positional) - len(fn.args.defaults)
                for index, default in enumerate(fn.args.defaults):
                    if not isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        continue
                    name = (
                        positional[offset + index].arg
                        if 0 <= offset + index < len(positional)
                        else f"arg{index}"
                    )
                    found.append(Violation(
                        key=f"mutable::{key}::{name}",
                        path=path, line=fn.lineno,
                        message=f"{path}:{fn.lineno} {fn.name} mutable default for {name}",
                        evidence=f"{path}:{fn.lineno} {fn.name}({name}=...)",
                        suggestion=(
                            "Use None as the default and create the container inside "
                            "the function."
                        ),
                    ))
                for index, default in enumerate(fn.args.kw_defaults):
                    if default is None or not isinstance(default, (ast.List, ast.Dict, ast.Set)):
                        continue
                    name = (
                        fn.args.kwonlyargs[index].arg
                        if index < len(fn.args.kwonlyargs)
                        else f"kwarg{index}"
                    )
                    found.append(Violation(
                        key=f"mutable::{key}::{name}",
                        path=path, line=fn.lineno,
                        message=f"{path}:{fn.lineno} {fn.name} mutable default for {name}",
                        evidence=f"{path}:{fn.lineno} {fn.name}({name}=...)",
                        suggestion=(
                            "Use None as the default and create the container inside "
                            "the function."
                        ),
                    ))
        return found

    def evaluate(self, ctx: RuleContext) -> RuleResult:
        error = ctx.relevant_error()
        if error:
            return RuleResult.unknown(self.id, f"cannot evaluate: {error}", evidence=error)
        violations = self._check(ctx.after_asts())
        if not violations:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="ok")
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion, violations=violations,
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
        violations: list[Violation] = []
        checked = 0
        for path, tree in sorted(ctx.after_asts().items()):
            for owner, fn, occurrence in _function_entries(tree):
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
                if any(_matches(d, self.decorator) for d in decos):
                    continue
                violations.append(Violation(
                    key=f"decorator::{_function_key(owner, fn, occurrence)}::{self.decorator}",
                    path=path, line=fn.lineno,
                    message=f"{fn.name} missing @{self.decorator}",
                    evidence=f"{path}:{fn.lineno} decorators={decos}",
                    suggestion=f"Add @{self.decorator} to {fn.name}.",
                ))
        if checked == 0 and self.required:
            violations.append(Violation(
                key="missing-target", path="", line=0,
                message=f"target function {self.function.pattern} not found",
                evidence=f"target function {self.function.pattern} not found",
                suggestion="Add the function or set required=false for an optional rule.",
                missing_target=True,
            ))
        if not violations:
            return RuleResult(rule_id=self.id, outcome=Outcome.PASS, message="ok")
        first = violations[0]
        return RuleResult(
            rule_id=self.id, outcome=Outcome.FAIL, message=first.message,
            path=first.path, line=first.line,
            evidence="; ".join(v.evidence for v in violations),
            suggestion=first.suggestion,
            missing_target=any(v.missing_target for v in violations),
            violations=violations,
        )


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
