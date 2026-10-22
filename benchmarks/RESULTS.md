# Benchmark Results

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

## Aggregate

| Metric | Value |
|---|---|
| Scenarios | 23 |
| True positives | 15 |
| False positives | 0 |
| True negatives | 8 |
| False negatives | 0 |
| Precision | 100.00% |
| Recall | 100.00% |
| F1 | 100.00% |
| Accuracy | 100.00% |
| False-positive rate | 0.00% |
| Unknown results | 0 |
| Incomplete scenarios | 0 |

## Per scenario

| Scenario | Category | Expected | Predicted | Correct |
|---|---|---|---|---|
| `layer-violation-direct-db` | introduced-violation | block | block | ✅ |
| `layer-safe-rename` | safe-refactor | allow | allow | ✅ |
| `layer-violation-auth-order` | introduced-violation | block | block | ✅ |
| `layer-safe-add-method` | safe-refactor | allow | allow | ✅ |
| `layer-orphaned-calls` | introduced-violation | block | block | ✅ |
| `layer-preexisting-debt` | preexisting-debt | allow | allow | ✅ |
| `layer-existing-plus-new-import-same-file` | introduced-violation | block | block | ✅ |
| `layer-existing-plus-new-import-other-file` | introduced-violation | block | block | ✅ |
| `layer-rename-preexisting-debt` | safe-refactor | allow | allow | ✅ |
| `layer-preexisting-parse-error-unrelated` | safe-refactor | allow | allow | ✅ |
| `auth-existing-plus-new-failing-function` | introduced-violation | block | block | ✅ |
| `auth-repaired-old-plus-new-failing-function` | introduced-violation | block | block | ✅ |
| `auth-missing-authorize-delete` | introduced-violation | block | block | ✅ |
| `auth-missing-authorize-transfer` | introduced-violation | block | block | ✅ |
| `auth-safe-logging` | safe-refactor | allow | allow | ✅ |
| `auth-mutable-default` | introduced-violation | block | block | ✅ |
| `auth-missing-annotation` | introduced-violation | block | block | ✅ |
| `pricing-float-regression` | introduced-violation | block | block | ✅ |
| `pricing-negative-total` | introduced-violation | block | block | ✅ |
| `pricing-safe-refactor` | safe-refactor | allow | allow | ✅ |
| `plugin-registry-importlib` | introduced-violation | block | block | ✅ |
| `plugin-registry-eval` | introduced-violation | block | block | ✅ |
| `plugin-safe-logging` | safe-refactor | allow | allow | ✅ |
