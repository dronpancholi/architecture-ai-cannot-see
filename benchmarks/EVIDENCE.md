# Evidence: Agent With vs. Without the Verification Loop

Ground truth is the scenario label, not the verifier's own verdict.
Baseline commits the first proposal. The verified loop reads feedback and revises.

## Aggregate

| Metric | Baseline | With verification loop |
|---|---|---|
| Changes that are actually safe | 8/23 (35%) | 23/23 (100%) |
| Unsafe changes committed | 15/23 | 0/23 |
| Average iterations | 1.0 | 1.7 |
| Average verification overhead | 0 ms | 30.2 ms |

## Per scenario

| Scenario | Baseline safe | Loop safe | Iterations | Verify (ms) |
|---|---|---|---|---|
| `layer-violation-direct-db` | ❌ | ✅ | 2 | 15.1 |
| `layer-safe-rename` | ✅ | ✅ | 1 | 7.1 |
| `layer-violation-auth-order` | ❌ | ✅ | 2 | 15.0 |
| `layer-safe-add-method` | ✅ | ✅ | 1 | 8.0 |
| `layer-orphaned-calls` | ❌ | ✅ | 2 | 15.9 |
| `layer-preexisting-debt` | ✅ | ✅ | 1 | 7.6 |
| `layer-existing-plus-new-import-same-file` | ❌ | ✅ | 2 | 14.9 |
| `layer-existing-plus-new-import-other-file` | ❌ | ✅ | 2 | 15.6 |
| `layer-rename-preexisting-debt` | ✅ | ✅ | 1 | 7.1 |
| `layer-preexisting-parse-error-unrelated` | ✅ | ✅ | 1 | 6.9 |
| `auth-existing-plus-new-failing-function` | ❌ | ✅ | 2 | 8.8 |
| `auth-repaired-old-plus-new-failing-function` | ❌ | ✅ | 2 | 8.6 |
| `auth-missing-authorize-delete` | ❌ | ✅ | 2 | 10.1 |
| `auth-missing-authorize-transfer` | ❌ | ✅ | 2 | 9.9 |
| `auth-safe-logging` | ✅ | ✅ | 1 | 5.0 |
| `auth-mutable-default` | ❌ | ✅ | 2 | 10.4 |
| `auth-missing-annotation` | ❌ | ✅ | 2 | 10.5 |
| `pricing-float-regression` | ❌ | ✅ | 2 | 200.2 |
| `pricing-negative-total` | ❌ | ✅ | 2 | 198.6 |
| `pricing-safe-refactor` | ✅ | ✅ | 1 | 103.7 |
| `plugin-registry-importlib` | ❌ | ✅ | 2 | 7.0 |
| `plugin-registry-eval` | ❌ | ✅ | 2 | 6.5 |
| `plugin-safe-logging` | ✅ | ✅ | 1 | 3.2 |
