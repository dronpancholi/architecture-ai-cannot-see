# Architecture

Mirrors the whitepaper's three reasoning layers, plus the verification and agent layers that make it usable.

## Representation Layer (`src/knowledge_surface/representation/`)

- `entities.py` — `Entity`, `Relationship`, `Invariant`, `Confidence`, `Provenance`, `Location`. Confidence is first-class (KNOWN / INFERRED / UNKNOWN).
- `knowledge_surface.py` — typed graph (networkx DiGraph), invariants, dependents/dependencies, serialization.
- `invariants.py` — `InvariantRegistry` (human-declared, KNOWN) + `HeuristicInvariantExtractor` (INFERRED).

## Extractors (`src/knowledge_surface/extractors/`)

- `python_ast.py` — First Architecture from Python source; unresolved imports become UNKNOWN.
- `deep.py` — `CallGraphExtractor` (name-resolved call edges), `DynamicImportExtractor` (`importlib.import_module`, `__import__`, f-string prefixes), `FrameworkExtractor` (decorator capabilities).

`pipeline.build_surface()` runs all of the above plus heuristic invariants.

## Verification Layer (`src/knowledge_surface/verification/`)

- `change.py` — `ChangeSet` / `FileChange`, unified-diff parsing, after-tree materialization.
- `rules.py` — rule types: `ForbiddenImportRule`, `ForbiddenCallRule`, `RequireCallRule` (owner-scoped), `TypeAnnotationRule`, `NoMutableDefaultRule`, `BehavioralRule`, `CustomRule`, `Allowlist`.
- `engine.py` — `SemanticVerifier`: evaluates rules on before and after trees; blocks only **introduced** failures; reports pre-existing debt and suppressed findings separately; runs behavioural rules in a subprocess with a timeout.
- `feedback.py` — machine-readable and Markdown feedback for an agent or human.
- `config.py` — JSON rule config.

## Reasoning Layer (`src/knowledge_surface/reasoning/`)

- `consistency.py` — entity/relationship consistency (the higher-level, scope-based check).
- `propagation.py` — blast radius and risk scoring.

## Action Layer (`src/knowledge_surface/action/`)

- `verified_action.py` — `ChangeEvaluator` produces `VerifiedAction` verdicts.

## Agent Layer (`src/knowledge_surface/agent/`)

- `loop.py` — `FeedbackLoop`, `ScriptedAgent`, `Baseline`.
- `llm_adapter.py` — `LLMAgent` over any `complete(prompt) -> str`.

## Drift (`src/knowledge_surface/drift/`)

- `detector.py` — duplicate concepts, invariant loss, confidence regression, naming divergence.

## Benchmarks (`benchmarks/`)

- `fixtures/` — realistic multi-module projects.
- `scenarios.py` — labelled violations, safe refactors, pre-existing debt.
- `runner.py` — precision / recall / F1 / FPR.
- `external.py` — pinned real public repo (`pallets/itsdangerous`).
- `agent_experiment.py` — baseline vs. verification loop.

## CLI (`src/knowledge_surface/cli.py`)

`ks build | inspect | query | check | verify | drift | report`.
