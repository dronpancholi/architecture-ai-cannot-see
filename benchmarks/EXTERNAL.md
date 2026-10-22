# External Benchmark — Real Public Repositories

- Tool: `knowledge-surface 0.3.1`
- Targets: 2
- Scenarios: 10
- Every checkout is pinned and HEAD-verified before scenarios run.
- Unknown or incomplete results fail the benchmark instead of counting as a block.

# pallets/itsdangerous @ `672971d66a2e`

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

- Repository: `https://github.com/pallets/itsdangerous.git`
- Commit: `672971d66a2ef9f85151e53283113f33d642dabd`

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
| Unknown results | 0 |
| Incomplete scenarios | 0 |

## Per scenario

| Scenario | Category | Expected | Predicted | Correct |
|---|---|---|---|---|
| `itsdangerous-constant-time` | introduced-violation | block | block | ✅ |
| `itsdangerous-signer-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-docstring` | safe-refactor | allow | allow | ✅ |
| `itsdangerous-pickle` | introduced-violation | block | block | ✅ |
| `itsdangerous-safe-rename` | safe-refactor | allow | allow | ✅ |

# psf/requests @ `611c6162cbc4`

Ground truth: a scenario labelled *block* introduces an architectural violation;
a scenario labelled *allow* is a safe refactor or pre-existing debt.

- Repository: `https://github.com/psf/requests.git`
- Commit: `611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60`

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
| Unknown results | 0 |
| Incomplete scenarios | 0 |

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
| Unknown results | 0 |
| Incomplete scenarios | 0 |

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
