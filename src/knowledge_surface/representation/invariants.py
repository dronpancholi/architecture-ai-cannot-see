"""Manual and semi-automatic invariant capture.

The Second Architecture cannot be fully recovered by static analysis.
This module lets engineers declare invariants explicitly (the honest path)
and provides a best-effort heuristic extractor that marks everything it
produces as INFERRED.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..paths import iter_python_files
from .entities import Confidence, Invariant, Provenance
from .knowledge_surface import KnowledgeSurface


class InvariantRegistry:
    """Declarative invariants: humans write them, machines enforce them."""

    def __init__(self) -> None:
        self._invariants: list[Invariant] = []

    def declare(
        self,
        name: str,
        description: str,
        scope: list[str],
        severity: str = "error",
        confidence: Confidence = Confidence.KNOWN,
        rationale: str = "",
    ) -> Invariant:
        inv = Invariant(
            id=Invariant.make_id(name),
            name=name,
            description=description,
            scope=scope,
            severity=severity,
            confidence=confidence,
            provenance=Provenance(created_by="engineer", rationale=rationale),
        )
        self._invariants.append(inv)
        return inv

    def apply(self, ks: KnowledgeSurface) -> None:
        for inv in self._invariants:
            ks.add_invariant(inv)

    def all(self) -> list[Invariant]:
        return list(self._invariants)


# Heuristic: lines like "# INVARIANT: ..." or docstrings containing "must"/"never"
_INVARIANT_RE = re.compile(r"(?:INVARIANT|CONSTRAINT|RULE)\s*[:\-]\s*(.+)", re.IGNORECASE)


class HeuristicInvariantExtractor:
    def __init__(self, root: str | Path):
        self.root = Path(root)

    def extract(self, ks: KnowledgeSurface) -> list[Invariant]:
        found: list[Invariant] = []
        for rel, f in iter_python_files(self.root):
            try:
                text = f.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for i, line in enumerate(text.splitlines(), 1):
                m = _INVARIANT_RE.search(line)
                if m:
                    desc = m.group(1).strip()
                    inv = Invariant(
                        id=Invariant.make_id(f"{rel}:{i}:{desc}"),
                        name=f"invariant@{rel}:{i}",
                        description=desc,
                        scope=[],
                        severity="warning",
                        confidence=Confidence.INFERRED,
                        provenance=Provenance(
                            created_by="extractor:heuristic", source=rel,
                            rationale="recovered from comment; scope unverified",
                        ),
                    )
                    found.append(inv)
        # attach with empty scope (honest: we don't know what it constrains)
        for inv in found:
            ks.add_invariant(inv)
        return found
