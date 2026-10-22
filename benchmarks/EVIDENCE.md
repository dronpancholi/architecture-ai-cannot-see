# Evidence: Agent With vs. Without the Verification Loop

Ground truth is the scenario label, not the verifier's own verdict.
Baseline commits the first proposal. The verified loop reads feedback and revises.

## Aggregate

| Metric | Baseline | With verification loop |
|---|---|---|
| Changes that are actually safe | 6/17 (35%) | 17/17 (100%) |
| Unsafe changes committed | 11/17 | 0/17 |
| Average iterations | 1.0 | 1.6 |
| Average verification overhead | 0 ms | 26.5 ms |

## Per scenario

| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |
|---|---|---|---|---|
| `layer-violation-direct-db` | ❌ | ✅ | 2 | 19.1 |
| `layer-safe-rename` | ✅ | ✅ | 1 | 10.3 |
| `layer-violation-auth-order` | ❌ | ✅ | 2 | 27.8 |
| `layer-safe-add-method` | ✅ | ✅ | 1 | 6.1 |
| `layer-orphaned-calls` | ❌ | ✅ | 2 | 13.3 |
| `layer-preexisting-debt` | ✅ | ✅ | 1 | 6.2 |
| `auth-missing-authorize-delete` | ❌ | ✅ | 2 | 8.1 |
| `auth-missing-authorize-transfer` | ❌ | ✅ | 2 | 7.5 |
| `auth-safe-logging` | ✅ | ✅ | 1 | 4.0 |
| `auth-mutable-default` | ❌ | ✅ | 2 | 7.9 |
| `auth-missing-annotation` | ❌ | ✅ | 2 | 7.6 |
| `pricing-float-regression` | ❌ | ✅ | 2 | 129.8 |
| `pricing-negative-total` | ❌ | ✅ | 2 | 127.7 |
| `pricing-safe-refactor` | ✅ | ✅ | 1 | 61.9 |
| `plugin-registry-importlib` | ❌ | ✅ | 2 | 5.6 |
| `plugin-registry-eval` | ❌ | ✅ | 2 | 5.3 |
| `plugin-safe-logging` | ✅ | ✅ | 1 | 2.6 |
