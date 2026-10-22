# Evidence: Agent With vs. Without the Verification Loop

Ground truth is the scenario label, not the verifier's own verdict.
Baseline commits the first proposal. The verified loop reads feedback and revises.

## Aggregate

| Metric | Baseline | With verification loop |
|---|---|---|
| Changes that are actually safe | 6/17 (35%) | 17/17 (100%) |
| Unsafe changes committed | 11/17 | 0/17 |
| Average iterations | 1.0 | 1.6 |
| Average verification overhead | 0 ms | 60.4 ms |

## Per scenario

| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |
|---|---|---|---|---|
| `layer-violation-direct-db` | ❌ | ✅ | 2 | 21.8 |
| `layer-safe-rename` | ✅ | ✅ | 1 | 9.8 |
| `layer-violation-auth-order` | ❌ | ✅ | 2 | 21.2 |
| `layer-safe-add-method` | ✅ | ✅ | 1 | 11.2 |
| `layer-orphaned-calls` | ❌ | ✅ | 2 | 26.4 |
| `layer-preexisting-debt` | ✅ | ✅ | 1 | 12.1 |
| `auth-missing-authorize-delete` | ❌ | ✅ | 2 | 14.3 |
| `auth-missing-authorize-transfer` | ❌ | ✅ | 2 | 14.6 |
| `auth-safe-logging` | ✅ | ✅ | 1 | 7.4 |
| `auth-mutable-default` | ❌ | ✅ | 2 | 14.0 |
| `auth-missing-annotation` | ❌ | ✅ | 2 | 15.8 |
| `pricing-float-regression` | ❌ | ✅ | 2 | 325.9 |
| `pricing-negative-total` | ❌ | ✅ | 2 | 337.4 |
| `pricing-safe-refactor` | ✅ | ✅ | 1 | 165.8 |
| `plugin-registry-importlib` | ❌ | ✅ | 2 | 12.1 |
| `plugin-registry-eval` | ❌ | ✅ | 2 | 12.2 |
| `plugin-safe-logging` | ✅ | ✅ | 1 | 5.5 |
