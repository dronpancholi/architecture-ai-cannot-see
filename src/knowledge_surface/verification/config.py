"""Load verifier rules from a JSON file (for CLI and CI use)."""

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
    Rule,
    TypeAnnotationRule,
)

_TYPES = {
    "forbidden_import": ForbiddenImportRule,
    "forbidden_call": ForbiddenCallRule,
    "require_call": RequireCallRule,
    "type_annotation": TypeAnnotationRule,
    "no_mutable_default": NoMutableDefaultRule,
    "behavioral": BehavioralRule,
}


def load_rules(config_path: str | Path) -> tuple[list[Rule], Allowlist]:
    data = json.loads(Path(config_path).read_text())
    rules: list[Rule] = []
    for spec in data.get("rules", []):
        kind = spec.pop("type")
        if kind not in _TYPES:
            raise ValueError(f"unknown rule type: {kind}")
        rules.append(_TYPES[kind](**spec))
    allow = Allowlist([tuple(x) for x in data.get("allowlist", [])])
    return rules, allow
