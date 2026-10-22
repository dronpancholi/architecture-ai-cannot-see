# Benchmarks

Evidence that the verifier works, and an honest account of what it does not prove.

## Run

```bash
python benchmarks/runner.py            # controlled fixtures -> RESULTS.md
python benchmarks/external.py          # real public repos  -> EXTERNAL.md
python benchmarks/agent_experiment.py  # baseline vs loop  -> EVIDENCE.md
python benchmarks/perf.py              # local latency/memory -> perf.json
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

The suite includes old-debt-plus-new-violation cases, a file rename that preserves debt, and a scoped rule with an unrelated pre-existing parse error. A new parse error in a changed file is covered by tests rather than this score, because it is deliberately incomplete/blocking.

The label is the ground truth. The verifier never grades itself.

## Targets

| Benchmark | Target | Scenarios |
|---|---|---|
| `runner.py` | 4 realistic multi-module fixtures | 23 |
| `external.py` | `pallets/itsdangerous`, `psf/requests` (pinned) | 10 |
| `agent_experiment.py` | same 23 scenarios, baseline vs loop | 23 |
| `perf.py` | project source + layered fixture (single host) | n/a |

## Honest limits

- The controlled fixtures are designed alongside the rules. A perfect score there shows the engine implements the rules correctly; it does not show the rules generalise.
- The external benchmark is real code at exact pinned commits (HEAD verified), but 10 scenarios over 2 repositories is a signal, not a proof.
- `perf.py` is a regression baseline on one host, not a comparison with other tools. Numbers vary with machine load; `perf.json` records the latest run.
- The agent experiment's revision is a deterministic safe repair. It measures gating and convergence, not LLM repair quality.
- Rules are only as good as their declarations. The engine cannot invent an invariant that was never written.
