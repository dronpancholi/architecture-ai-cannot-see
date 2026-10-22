"""Knowledge Surface: structured representation of software's two architectures."""

from .action.verified_action import ChangeEvaluator, VerifiedAction
from .drift.detector import DriftReport, SemanticDriftDetector
from .extractors.python_ast import PythonASTExtractor
from .reasoning.consistency import ConsistencyChecker, ConsistencyVerdict
from .reasoning.propagation import PropagationAnalyzer, RiskScorer
from .representation.entities import (
    Confidence,
    Entity,
    EntityKind,
    Invariant,
    Location,
    Provenance,
    RelationKind,
    Relationship,
)
from .representation.invariants import HeuristicInvariantExtractor, InvariantRegistry
from .representation.knowledge_surface import KnowledgeSurface

__all__ = [
    "Confidence", "Entity", "EntityKind", "Invariant", "Location", "Provenance",
    "Relationship", "RelationKind", "KnowledgeSurface", "InvariantRegistry",
    "HeuristicInvariantExtractor", "PythonASTExtractor", "ConsistencyChecker",
    "ConsistencyVerdict", "PropagationAnalyzer", "RiskScorer", "ChangeEvaluator",
    "VerifiedAction", "SemanticDriftDetector", "DriftReport",
]
__version__ = "0.1.0"
