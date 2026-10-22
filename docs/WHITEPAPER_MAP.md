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
| 1. Real semantic verification | Rules evaluate before/after trees; `BehavioralRule` executes assertions | `verification/engine.py`, `tests/test_verification.py` |
| 2. A real benchmark | 17 labelled scenarios + external pinned repo | `benchmarks/RESULTS.md`, `benchmarks/EXTERNAL.md` |
| 3. False-positive control | Regression-only blocking + allowlist; pre-existing debt never blocks | `tests/test_verification.py::test_preexisting_debt_not_blocking` |
| 4. Deeper code understanding | Call graph, dynamic imports, framework decorators, owner-scoped functions | `extractors/deep.py`, `tests/test_deep_extractors.py` |
| 5. Complete agent loop | `FeedbackLoop` with actionable feedback and revision | `agent/loop.py`, `tests/test_agent_and_benchmark.py` |
| 6. Evidence of superiority | Baseline vs. loop experiment on labelled scenarios | `benchmarks/EVIDENCE.md` |

## Demonstrations

- `examples/demo_codebase/` — invariant lives nowhere (comment only).
- `examples/demo_codebase_v2/` — drifted: invariant lost, duplicate Money concept.
- `examples/bad.patch` + `examples/ks-rules.json` — CLI verification gate.
