"""Core entity and relationship types for the Knowledge Surface.

These types encode the first requirement of a correct representation:
system-scope (entities are the unit of reasoning, not files) and
honest uncertainty (confidence is a first-class value).
"""

from __future__ import annotations

import hashlib
from datetime import datetime
from enum import StrEnum as Enum
from typing import Any

from pydantic import BaseModel, Field


class Confidence(Enum):
    """Honest uncertainty: how well do we know this fact?"""

    KNOWN = "known"          # directly observed / parsed from source
    INFERRED = "inferred"    # derived by analysis, may be wrong
    UNKNOWN = "unknown"      # not established


class EntityKind(Enum):
    MODULE = "module"
    CLASS = "class"
    FUNCTION = "function"
    INVARIANT = "invariant"
    CAPABILITY = "capability"
    DECISION = "decision"
    CONSTRAINT = "constraint"


class RelationKind(Enum):
    IMPORTS = "imports"
    CALLS = "calls"
    IMPLEMENTS = "implements"
    REQUIRES = "requires"            # capability requirement
    CONSTRAINS = "constrains"        # invariant constrains entity
    DECIDED_BY = "decided_by"        # provenance
    DEPENDS_ON = "depends_on"
    DUPLICATES = "duplicates"        # semantic drift: same concept, two impls


class Location(BaseModel):
    file: str
    start_line: int = 0
    end_line: int = 0

    def __str__(self) -> str:
        return f"{self.file}:{self.start_line}-{self.end_line}"


class Provenance(BaseModel):
    """Why does this entity exist? What decision created it?

    ``timestamp`` is optional so repeated extraction from the same source is
    byte-for-byte deterministic. Callers that know the time can set it.
    """

    created_by: str = "unknown"          # author / session / tool
    rationale: str = ""
    timestamp: datetime | None = None    # optional: keeps serialization deterministic
    source: str = ""                     # commit, doc, or conversation ref


class Entity(BaseModel):
    id: str
    kind: EntityKind
    name: str
    location: Location | None = None
    confidence: Confidence = Confidence.KNOWN
    provenance: Provenance = Field(default_factory=Provenance)
    attributes: dict[str, Any] = Field(default_factory=dict)

    @staticmethod
    def make_id(kind: EntityKind, name: str, file: str = "") -> str:
        raw = f"{kind.value}:{name}:{file}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


class Relationship(BaseModel):
    id: str
    source: str                          # entity id
    target: str                          # entity id
    kind: RelationKind
    confidence: Confidence = Confidence.KNOWN
    evidence: str = ""                   # human-readable justification
    provenance: Provenance = Field(default_factory=Provenance)

    @staticmethod
    def make_id(source: str, kind: RelationKind, target: str) -> str:
        raw = f"{source}-{kind.value}-{target}"
        return hashlib.sha1(raw.encode()).hexdigest()[:12]


class Invariant(BaseModel):
    """A constraint that must be preserved for the system to behave correctly.

    Invariants are the heart of the Second Architecture: they rarely live
    in any file, yet they are what makes modification safe.
    """

    id: str
    name: str
    description: str
    scope: list[str] = Field(default_factory=list)   # entity ids this constrains
    severity: str = "error"                          # error | warning | info
    confidence: Confidence = Confidence.INFERRED
    provenance: Provenance = Field(default_factory=Provenance)

    @staticmethod
    def make_id(name: str) -> str:
        return hashlib.sha1(name.encode()).hexdigest()[:12]
