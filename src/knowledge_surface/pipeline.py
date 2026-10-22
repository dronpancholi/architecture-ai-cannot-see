"""One-call pipeline: source tree -> enriched Knowledge Surface."""

from __future__ import annotations

from pathlib import Path

from .extractors.deep import CallGraphExtractor, DynamicImportExtractor, FrameworkExtractor
from .extractors.python_ast import PythonASTExtractor
from .representation.invariants import HeuristicInvariantExtractor
from .representation.knowledge_surface import KnowledgeSurface


def build_surface(root: str | Path, name: str = "knowledge-surface", deep: bool = True) -> KnowledgeSurface:
    root = Path(root)
    ks = PythonASTExtractor(root).build(name=name)
    if deep:
        CallGraphExtractor().enrich(ks, root)
        DynamicImportExtractor().enrich(ks, root)
        FrameworkExtractor().enrich(ks, root)
    HeuristicInvariantExtractor(root).extract(ks)
    return ks
