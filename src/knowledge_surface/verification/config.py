"""Load verifier rules from a JSON file (for CLI and CI use).

The config is deliberately small and explicit. Behavioural snippets are
untrusted by default; set ``"trusted": true`` only for project-authored code,
or run the verifier inside real isolation and pass the CLI override.
"""

from __future__ import annotations

import json
from pathlib import Path

from .rules import (
    Allowlist,
    BehavioralRule,
    ForbiddenCallRule,
    ForbiddenImportRule,
    NoMutableDefaultRule,
    RequireCallRule,
    RequiredDecoratorRule,
    Rule,
    TypeAnnotationRule,
)

_TYPES = {
    "forbidden_import": ForbiddenImportRule,
    "forbidden_call": ForbiddenCallRule,
    "require_call": RequireCallRule,
    "required_decorator": RequiredDecoratorRule,
    "type_annotation": TypeAnnotationRule,
    "no_mutable_default": NoMutableDefaultRule,
    "behavioral": BehavioralRule,
}


def load_rules(config_path: str | Path) -> tuple[list[Rule], Allowlist]:
    raw = Path(config_path).read_text(encoding="utf-8")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("rule config must be a JSON object")
    rules_spec = data.get("rules", [])
    if not isinstance(rules_spec, list):
        raise ValueError("rules must be a list")
    rules: list[Rule] = []
    for index, spec in enumerate(rules_spec):
        if not isinstance(spec, dict):
            raise ValueError(f"rules[{index}] must be an object")
        spec = dict(spec)
        kind = spec.pop("type", None)
        if kind not in _TYPES:
            raise ValueError(f"rules[{index}]: unknown rule type: {kind!r}")
        cls = _TYPES[kind]
        try:
            rules.append(cls(**spec))
        except TypeError as exc:
            raise ValueError(f"rules[{index}] ({kind}): {exc}") from exc
    allow_spec = data.get("allowlist", [])
    if not isinstance(allow_spec, list):
        raise ValueError("allowlist must be a list")
    return rules, Allowlist([tuple(entry) for entry in allow_spec])
