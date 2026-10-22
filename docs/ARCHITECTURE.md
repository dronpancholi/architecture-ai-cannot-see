# Architecture

Mirrors the whitepaper's three reasoning layers.

## Representation Layer (`src/knowledge_surface/representation/`)

- `entities.py` — `Entity`, `Relationship`, `Invariant`, `Confidence`, `Provenance`, `Location`. Confidence is a first-class value (KNOWN / INFERRED / UNKNOWN) — honest uncertainty.
- `knowledge_surface.py` — the `KnowledgeSurface` store: typed graph (networkx DiGraph), invariants, dependents/dependencies, serialization.
- `invariants.py` — `InvariantRegistry` (human-declared, KNOWN) + `HeuristicInvariantExtractor` (INFERRED, honest about limits).

## Extractors (`src/knowledge_surface/extractors/`)

- `python_ast.py` — cold-start extractor recovering the First Architecture from Python source. External/unresolved imports become UNKNOWN-confidence synthetic modules.

## Reasoning Layer (`src/knowledge_surface/reasoning/`)

- `consistency.py` — `ConsistencyChecker`: add/remove entity, add relationship, free-form change. Returns `ConsistencyVerdict` with violations and unknowns. Inversion of burden of proof: a change touching an invariant's scope is flagged.
- `propagation.py` — `PropagationAnalyzer` (blast radius, affected invariants) and `RiskScorer` (fan-in/out, invariant count, unknown neighbors).

## Action Layer (`src/knowledge_surface/action/`)

- `verified_action.py` — `ChangeEvaluator` orchestrates reasoning; produces `VerifiedAction` (approved/flagged) with explanation. Actions are not "executed" here; they are gated.

## Drift (`src/knowledge_surface/drift/`)

- `detector.py` — `SemanticDriftDetector`: duplicate concepts, invariant loss, confidence regression, naming divergence.

## CLI (`src/knowledge_surface/cli.py`)

`ks build | inspect | query | check | drift | report`.
