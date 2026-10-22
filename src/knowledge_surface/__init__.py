"""Knowledge Surface: structured representation of software's two architectures."""

from .action.verified_action import ChangeEvaluator, VerifiedAction
from .agent.loop import Baseline, FeedbackLoop, ScriptedAgent
from .drift.detector import DriftReport, SemanticDriftDetector
from .extractors.python_ast import PythonASTExtractor
from .pipeline import build_surface
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
from .verification.change import ChangeSet, FileChange
from .verification.engine import SemanticVerifier, VerificationReport
from .verification.rules import (
    Allowlist,
    BehavioralRule,
    ForbiddenCallRule,
    ForbiddenImportRule,
    NoMutableDefaultRule,
    RequireCallRule,
    Rule,
    TypeAnnotationRule,
)

__all__ = [
    "Confidence", "Entity", "EntityKind", "Invariant", "Location", "Provenance",
    "Relationship", "RelationKind", "KnowledgeSurface", "InvariantRegistry",
    "HeuristicInvariantExtractor", "PythonASTExtractor", "ConsistencyChecker",
    "ConsistencyVerdict", "PropagationAnalyzer", "RiskScorer", "ChangeEvaluator",
    "VerifiedAction", "SemanticDriftDetector", "DriftReport", "build_surface",
    "ChangeSet", "FileChange", "SemanticVerifier", "VerificationReport",
    "Allowlist", "BehavioralRule", "ForbiddenCallRule", "ForbiddenImportRule",
    "NoMutableDefaultRule", "RequireCallRule", "Rule", "TypeAnnotationRule",
    "Baseline", "FeedbackLoop", "ScriptedAgent",
]
__version__ = "0.2.0"
