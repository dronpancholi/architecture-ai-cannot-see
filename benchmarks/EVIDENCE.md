# Evidence: Agent With vs. Without the Verification Loop

Ground truth is the scenario label, not the verifier's own verdict.
Baseline commits the first proposal. The verified loop reads feedback and revises.

## Aggregate

| Metric | Baseline | With verification loop |
|---|---|---|
| Changes that are actually safe | 6/16 (38%) | 16/16 (100%) |
| Unsafe changes committed | 10/16 | 0/16 |
| Average iterations | 1.0 | 1.6 |
| Average verification overhead | 0 ms | 38.5 ms |

## Per scenario

| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |
|---|---|---|---|---|
| `layer-violation-direct-db` | ❌ | ✅ | 2 | 17.2 |
| `layer-safe-rename` | ✅ | ✅ | 1 | 7.8 |
| `layer-violation-auth-order` | ❌ | ✅ | 2 | 19.1 |
| `layer-safe-add-method` | ✅ | ✅ | 1 | 9.7 |
| `layer-preexisting-debt` | ✅ | ✅ | 1 | 7.7 |
| `auth-missing-authorize-delete` | ❌ | ✅ | 2 | 10.1 |
| `auth-missing-authorize-transfer` | ❌ | ✅ | 2 | 11.8 |
| `auth-safe-logging` | ✅ | ✅ | 1 | 7.5 |
| `auth-mutable-default` | ❌ | ✅ | 2 | 18.1 |
| `auth-missing-annotation` | ❌ | ✅ | 2 | 15.2 |
| `pricing-float-regression` | ❌ | ✅ | 2 | 177.7 |
| `pricing-negative-total` | ❌ | ✅ | 2 | 194.5 |
| `pricing-safe-refactor` | ✅ | ✅ | 1 | 92.4 |
| `plugin-registry-importlib` | ❌ | ✅ | 2 | 8.3 |
| `plugin-registry-eval` | ❌ | ✅ | 2 | 15.7 |
| `plugin-safe-logging` | ✅ | ✅ | 1 | 3.8 |
