# Evidence: Agent With vs. Without the Verification Loop

Ground truth is the scenario label, not the verifier's own verdict.
Baseline commits the first proposal. The verified loop reads feedback and revises.

## Aggregate

| Metric | Baseline | With verification loop |
|---|---|---|
| Changes that are actually safe | 8/23 (35%) | 23/23 (100%) |
| Unsafe changes committed | 15/23 | 0/23 |
| Average iterations | 1.0 | 1.7 |
| Average verification overhead | 0 ms | 28.1 ms |

## Per scenario

| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |
|---|---|---|---|---|
| `layer-violation-direct-db` | ❌ | ✅ | 2 | 15.9 |
| `layer-safe-rename` | ✅ | ✅ | 1 | 6.8 |
| `layer-violation-auth-order` | ❌ | ✅ | 2 | 14.5 |
| `layer-safe-add-method` | ✅ | ✅ | 1 | 7.1 |
| `layer-orphaned-calls` | ❌ | ✅ | 2 | 17.3 |
| `layer-preexisting-debt` | ✅ | ✅ | 1 | 8.0 |
| `layer-existing-plus-new-import-same-file` | ❌ | ✅ | 2 | 14.4 |
| `layer-existing-plus-new-import-other-file` | ❌ | ✅ | 2 | 16.7 |
| `layer-rename-preexisting-debt` | ✅ | ✅ | 1 | 7.3 |
| `layer-preexisting-parse-error-unrelated` | ✅ | ✅ | 1 | 6.9 |
| `auth-existing-plus-new-failing-function` | ❌ | ✅ | 2 | 8.2 |
| `auth-repaired-old-plus-new-failing-function` | ❌ | ✅ | 2 | 8.6 |
| `auth-missing-authorize-delete` | ❌ | ✅ | 2 | 10.0 |
| `auth-missing-authorize-transfer` | ❌ | ✅ | 2 | 9.7 |
| `auth-safe-logging` | ✅ | ✅ | 1 | 5.6 |
| `auth-mutable-default` | ❌ | ✅ | 2 | 10.2 |
| `auth-missing-annotation` | ❌ | ✅ | 2 | 10.2 |
| `pricing-float-regression` | ❌ | ✅ | 2 | 183.4 |
| `pricing-negative-total` | ❌ | ✅ | 2 | 179.8 |
| `pricing-safe-refactor` | ✅ | ✅ | 1 | 88.5 |
| `plugin-registry-importlib` | ❌ | ✅ | 2 | 6.4 |
| `plugin-registry-eval` | ❌ | ✅ | 2 | 6.2 |
| `plugin-safe-logging` | ✅ | ✅ | 1 | 3.3 |
