# Benchmarks

Evidence that the verifier works, and an honest account of what it does not prove.

## Run

```bash
python benchmarks/runner.py            # controlled fixtures -> RESULTS.md
python benchmarks/external.py          # real public repos  -> EXTERNAL.md
python benchmarks/agent_experiment.py  # baseline vs loop  -> EVIDENCE.md
```

## What is measured

- **Precision** — of the changes we block, how many were real violations?
- **Recall** — of the real violations, how many did we block?
- **False-positive rate** — of the safe changes, how many did we wrongly block?
- **Accuracy**, **F1** — aggregate summaries.

## Ground truth

Each scenario is labelled by construction:

- `introduced-violation` — the change adds a known architectural violation (must block).
- `safe-refactor` — the change preserves all invariants (must allow).
- `preexisting-debt` — the violation existed before the change (must not block).

The label is the ground truth. The verifier never grades itself.

## Targets

| Benchmark | Target | Scenarios |
|---|---|---|
| `runner.py` | 4 realistic multi-module fixtures | 17 |
| `external.py` | `pallets/itsdangerous`, `psf/requests` (pinned) | 10 |
| `agent_experiment.py` | same 17 scenarios, baseline vs loop | 17 |

## Honest limits

- The controlled fixtures are designed alongside the rules. A perfect score there shows the engine implements the rules correctly; it does not show the rules generalise.
- The external benchmark is real code, but 10 scenarios over 2 repositories is a signal, not a proof.
- The agent experiment's revision is a deterministic safe repair. It measures gating and convergence, not LLM repair quality.
- Rules are only as good as their declarations. The engine cannot invent an invariant that was never written.
