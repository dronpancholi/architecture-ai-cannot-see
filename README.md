# The Architecture AI Cannot See — Knowledge Surface

> *"Every production system has two architectures: the one in the files, and the one that lives nowhere. We taught AI to read the first. The second is the one that matters."*

A reference implementation of the **Knowledge Surface** — a structured, queryable representation of *both* architectures of a software system — as described in the whitepaper [`WHITEPAPER.md`](./WHITEPAPER.md).

## Why

AI coding agents are celebrated for generating code, but deployed into real codebases they fix one function and break two others they never touched. The cause is not intelligence or context length. It is a **representation problem**: agents reason over files (a flat sequence of tokens), while software is a network of modules, invariants, capability contracts and decisions. Context is not comprehension.

This project demonstrates the fix: build a richer substrate. The Knowledge Surface captures entities, typed relationships, invariants (the Second Architecture), and provenance, with honest uncertainty. A Reasoning Layer evaluates proposed changes against it before they become commits. A drift detector surfaces semantic incoherence across sessions.

## Install

```bash
pip install -e .
```

## Quick start

```bash
# Build a Knowledge Surface from a codebase
ks build examples/demo_codebase -o ks.json

# Inspect
ks inspect ks.json

# Reason about a change
ks check ks.json <entity-id> --action remove

# Detect semantic drift between two snapshots
ks build examples/demo_codebase -o before.json
ks build examples/demo_codebase_v2 -o after.json
ks drift before.json after.json
```

## Python API

```python
from knowledge_surface import PythonASTExtractor, InvariantRegistry, ChangeEvaluator, Confidence

ks = PythonASTExtractor("src/").build()
reg = InvariantRegistry()
reg.declare(
    name="credit-limit",
    description="an order's total must never exceed the customer's credit limit",
    scope=[order_service_id],
    severity="error",
    confidence=Confidence.KNOWN,
    rationale="enforced by review culture; absent from code",
)
reg.apply(ks)

ev = ChangeEvaluator(ks)
verdict = ev.evaluate_remove_entity(order_service_id)
print(verdict.approved, verdict.verdict.summary())
```

## What is proven (tests)

- `tests/test_entities.py` — entities, relationships, honest uncertainty
- `tests/test_knowledge_surface.py` — graph reasoning, serialization, unknowns
- `tests/test_consistency.py` — inversion of burden of proof: load-bearing removals blocked
- `tests/test_propagation.py` — blast radius and risk scoring
- `tests/test_drift.py` — semantic drift detection across sessions
- `tests/test_whitepaper_claims.py` — direct proofs of whitepaper claims

Run: `pytest -q`

## Architecture

See [`docs/ARCHITECTURE.md`](./docs/ARCHITECTURE.md). Three layers: Representation → Reasoning → Action, mirroring the whitepaper's conceptual architecture.

## License

MIT. Whitepaper text © its author; reproduced for demonstration.
