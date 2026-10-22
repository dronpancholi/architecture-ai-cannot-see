# Whitepaper → Implementation Map

Maps each section of `WHITEPAPER.md` ("The Architecture AI Cannot See") to code and tests in this repository.

| Whitepaper section | Concept | Implementation |
|---|---|---|
| I. Capability we celebrate | generation vs. understanding | README framing; `tests/test_whitepaper_claims.py` |
| II. More context doesn't close gap | representation > scale | `KnowledgeSurface` is a graph, not a sequence (`tests/test_whitepaper_claims.py::test_claim_representation_gap_is_structural`) |
| III. File is not the software | Representation Gap | `PythonASTExtractor` recovers only what files hold; external deps are `UNKNOWN` (`test_claim_files_are_not_software`) |
| IV. Architecture that lives nowhere | Second Architecture | `Invariant`, `InvariantRegistry`, `KnowledgeSurface.invariants()` |
| V. Semantic drift | drift across sessions | `SemanticDriftDetector` (`tests/test_drift.py`) |
| VI. Correct solution properties | 6 properties | system-scope (entities), semantic typing (RelationKind), invariant tracking, temporal persistence (snapshots), traceability (Provenance), honest uncertainty (Confidence) |
| VII. Conceptual architecture | Representation/Reasoning/Action layers | `representation/`, `reasoning/`, `action/` packages |
| VIII. What makes this hard | cold start, staleness, tacit knowledge, confidence, adoption | heuristic extractor marks INFERRED; unknowns surfaced; incremental (partial surfaces useful) |
| IX. Open questions | refusal policy, etc. | `ChangeEvaluator` returns approved/flagged; configurable via severity |

## Demonstrations

- `examples/demo_codebase/` — a codebase whose invariant lives nowhere (comment only).
- `examples/demo_codebase_v2/` — drifted version: invariant lost, duplicate Money concept.
- `examples/usage.py` — end-to-end: build, declare invariant, evaluate removal (blocked).
