# Architecture

Mirrors the whitepaper's three reasoning layers, plus the verification and agent layers that make it usable.

## Representation Layer (`src/knowledge_surface/representation/`)

- `entities.py` — `Entity`, `Relationship`, `Invariant`, `Confidence`, `Provenance`, `Location`. Confidence is first-class (KNOWN / INFERRED / UNKNOWN). Entity IDs for functions/classes include their definition line so duplicate names in one file cannot collide.
- `knowledge_surface.py` — typed graph (networkx DiGraph), invariants, dependents/dependencies, schema version, validation, deterministic serialization.
- `invariants.py` — `InvariantRegistry` (human-declared, KNOWN) + `HeuristicInvariantExtractor` (INFERRED).

## Extractors (`src/knowledge_surface/extractors/`)

- `python_ast.py` — First Architecture from Python source; unresolved imports become UNKNOWN; parse failures become UNKNOWN modules with diagnostics. Walks with an exclusion set, does not follow symlinks outside the root, and caps file count/size.
- `deep.py` — `CallGraphExtractor` (conservative name-resolved call edges; ambiguous or shadowed targets skipped and counted), `DynamicImportExtractor` (`importlib.import_module`, `__import__`, f-string prefixes), `FrameworkExtractor` (decorator capabilities).

`pipeline.build_surface()` runs all of the above plus heuristic invariants. Repeated builds from the same source are byte-for-byte deterministic; timestamps and duration are excluded from serialized output.

## Verification Layer (`src/knowledge_surface/verification/`)

- `change.py` — `ChangeSet` / `FileChange`, strict unified-diff application against a base tree, add/delete/rename/copy, multi-file/multi-hunk support, after-tree materialization.
- `paths.py` — shared path normalization and containment checks. Every path from a diff, rule, or model passes through this module before touching the filesystem.
- `rules.py` — rule types: `ForbiddenImportRule`, `ForbiddenCallRule`, `RequireCallRule` (owner-scoped, missing-target failure, nested-scope pruning, dominance), `RequiredDecoratorRule`, `TypeAnnotationRule`, `NoMutableDefaultRule`, `BehavioralRule`, `CustomRule`, `Allowlist`. Results are `PASS` / `FAIL` / `UNKNOWN`; built-in rules also return every independent `Violation` with a stable semantic key.
- `sandbox.py` — behavioral-rule process isolation: minimal environment, timeout, process-group kill, POSIX rlimits, bounded output, untrusted refusal by default.
- `engine.py` — `SemanticVerifier`: evaluates rules on before and after trees; matches findings by `(canonical_path, key)` and classifies each as introduced / pre-existing / unknown / improvement; applies `unknown_policy`; reports parse errors as introduced or pre-existing diagnostics.
- `feedback.py` — machine-readable and Markdown feedback for an agent or human, including unknown and parse-error feedback.
- `config.py` — JSON rule config with constructor validation and clear errors.

## Reasoning Layer (`src/knowledge_surface/reasoning/`)

- `consistency.py` — entity/relationship consistency (the higher-level, scope-based check).
- `propagation.py` — blast radius and risk scoring.

## Action Layer (`src/knowledge_surface/action/`)

- `verified_action.py` — `ChangeEvaluator` produces `VerifiedAction` verdicts.

## Agent Layer (`src/knowledge_surface/agent/`)

- `loop.py` — `FeedbackLoop`, `ScriptedAgent`, `Baseline`. Terminal states are `APPROVED`, `REJECTED`, `EXHAUSTED`, `AGENT_ERROR`, `VERIFIER_ERROR`, `INDETERMINATE`. The final candidate is always the last verified one.
- `llm_adapter.py` — `LLMAgent` over any `complete(prompt) -> str`. Context is bounded and focused, secrets are redacted, responses are schema-validated, and unsafe/duplicate paths are rejected.

## Drift (`src/knowledge_surface/drift/`)

- `detector.py` — duplicate concepts (pre-existing vs. new), invariant loss, confidence regression, naming divergence, relationship changes, provenance loss, partial extraction. Findings carry evidence, confidence, and a suggestion.

## Benchmarks (`benchmarks/`)

- `fixtures/` — realistic multi-module projects.
- `scenarios.py` — labelled violations, safe refactors, pre-existing debt.
- `runner.py` — precision / recall / F1 / FPR, plus unknown/incomplete counts.
- `external.py` — pinned real public repositories (`pallets/itsdangerous`, `psf/requests`); fetches the exact SHA, checks out detached, verifies `git rev-parse HEAD`, and records metadata.
- `agent_experiment.py` — baseline vs. verification loop.
- `perf.py` — local extraction / verification / sandbox latency and peak memory.

## CLI (`src/knowledge_surface/cli.py`)

`ks build | inspect | query | check | verify | drift | report`.

Exit codes: `0` success/approved, `1` policy rejection or query miss, `2` input error, `3` indeterminate under a blocking unknown policy.
