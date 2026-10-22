# External Benchmark — Real Public Repositories

# pallets/itsdangerous @ 672971d

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

## Aggregate

| Metric | Value |
|---|---|
| Scenarios | 5 |
| True positives | 3 |
| False positives | 0 |
| True negatives | 2 |
| False negatives | 0 |
| Precision | 100.00% |
| Recall | 100.00% |
| F1 | 100.00% |
| Accuracy | 100.00% |
| False-positive rate | 0.00% |

## Per scenario

| Scenario | Category | Expected | Predicted | Correct |
|---|---|---|---|---|
| `itsdangerous-constant-time` | introduced-violation | block | block | ✅ |
| `itsdangerous-signer-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-docstring` | safe-refactor | allow | allow | ✅ |
| `itsdangerous-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-rename` | safe-refactor | allow | allow | ✅ |

# psf/requests @ 611c616

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

## Aggregate

| Metric | Value |
|---|---|
| Scenarios | 5 |
| True positives | 3 |
| False positives | 0 |
| True negatives | 2 |
| False negatives | 0 |
| Precision | 100.00% |
| Recall | 100.00% |
| F1 | 100.00% |
| Accuracy | 100.00% |
| False-positive rate | 0.00% |

## Per scenario

| Scenario | Category | Expected | Predicted | Correct |
|---|---|---|---|---|
| `requests-eval` | introduced-violation | block | block | ✅ |
| `requests-pickle` | introduced-violation | block | block | ✅ |
| `requests-subprocess` | introduced-violation | block | block | ✅ |
| `requests-safe-docstring` | safe-refactor | allow | allow | ✅ |
| `requests-safe-rename` | safe-refactor | allow | allow | ✅ |

## Combined

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

## Aggregate

| Metric | Value |
|---|---|
| Scenarios | 10 |
| True positives | 6 |
| False positives | 0 |
| True negatives | 4 |
| False negatives | 0 |
| Precision | 100.00% |
| Recall | 100.00% |
| F1 | 100.00% |
| Accuracy | 100.00% |
| False-positive rate | 0.00% |

## Per scenario

| Scenario | Category | Expected | Predicted | Correct |
|---|---|---|---|---|
| `itsdangerous-constant-time` | introduced-violation | block | block | ✅ |
| `itsdangerous-signer-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-docstring` | safe-refactor | allow | allow | ✅ |
| `itsdangerous-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-rename` | safe-refactor | allow | allow | ✅ |
| `requests-eval` | introduced-violation | block | block | ✅ |
| `requests-pickle` | introduced-violation | block | block | ✅ |
| `requests-subprocess` | introduced-violation | block | block | ✅ |
| `requests-safe-docstring` | safe-refactor | allow | allow | ✅ |
| `requests-safe-rename` | safe-refactor | allow | allow | ✅ |
