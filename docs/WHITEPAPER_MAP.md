# Whitepaper → Implementation Map

Maps each section of `WHITEPAPER.md` ("The Architecture AI Cannot See") to code, tests, and measured evidence.

| Whitepaper section | Concept | Implementation / evidence |
|---|---|---|
| I. Capability we celebrate | generation vs. understanding | README; `tests/test_whitepaper_claims.py` |
| II. More context doesn't close gap | representation > scale | `KnowledgeSurface` is a graph (`tests/test_whitepaper_claims.py::test_claim_representation_gap_is_structural`) |
| III. File is not the software | Representation Gap | `PythonASTExtractor`; external imports `UNKNOWN` |
| IV. Architecture that lives nowhere | Second Architecture | `Invariant`, `InvariantRegistry`, `KnowledgeSurface.invariants()` |
| V. Semantic drift | drift across sessions | `SemanticDriftDetector` (`tests/test_drift.py`) |
| VI. Correct solution properties | system-scope, semantic typing, invariant tracking, temporal persistence, traceability, honest uncertainty | entities, `RelationKind`, invariants, snapshots, `Provenance`, `Confidence` |
| VII. Conceptual architecture | Representation / Reasoning / Action | `representation/`, `verification/` + `reasoning/`, `action/` + `agent/` |
| VIII. What makes this hard | cold start, staleness, tacit knowledge, confidence, adoption | heuristic extractor marks INFERRED; unknowns surfaced; allowlist + regression-only blocking |
| IX. Open questions | refusal policy, verification, completeness | `SemanticVerifier` blocks regressions; `benchmarks/` measures precision/recall/FPR |

## The six defects, addressed

| Defect | Response | Evidence |
|---|---|---|
| 1. Real semantic verification | Tri-state rules evaluate before/after trees; `BehavioralRule` executes bounded, trusted assertions | `verification/engine.py`, `verification/rules.py`, `verification/sandbox.py`, `tests/test_verification.py`, `tests/test_tristate.py`, `tests/test_sandbox.py` |
| 2. A real benchmark | 17 labelled scenarios + 2 external pinned repositories (HEAD-verified) | `benchmarks/RESULTS.md`, `benchmarks/EXTERNAL.md`, `tests/test_benchmark_pins.py` |
| 3. False-positive control | Regression-only blocking + allowlist; unknown never becomes pre-existing | `tests/test_verification.py::test_preexisting_debt_not_blocking`, `tests/test_tristate.py` |
| 4. Deeper code understanding | Conservative call graph (ambiguous/shadowed targets skipped), dynamic imports, framework decorators, owner-scoped functions | `extractors/deep.py`, `tests/test_deep_extractors.py`, `tests/test_extractors.py` |
| 5. Complete agent loop | `FeedbackLoop` with terminal states and actionable feedback; no unverified final candidate | `agent/loop.py`, `tests/test_agent_loop.py` |
| 6. Evidence of improvement (not general superiority) | Baseline vs. loop experiment on 17 labelled scenarios with a scripted agent | `benchmarks/EVIDENCE.md`, `docs/CLAIMS.md` |

## Demonstrations

- `examples/demo_codebase/` — invariant lives nowhere (comment only).
- `examples/demo_codebase_v2/` — drifted: invariant lost, duplicate Money concept.
- `examples/bad.patch` + `examples/ks-rules.json` — CLI verification gate.
