# Contributing

Thanks for improving Knowledge Surface. This project values **measured evidence over claims**: a change that adds a capability should come with a test, and a change that fixes a false positive or false negative should come with the scenario that proves it.

## Setup

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]"
.venv/bin/python -m pytest -q
```

Python 3.11+ is required. CI runs 3.11, 3.12, and 3.13.

## Before opening a pull request

```bash
ruff check .
python -m pytest --cov=knowledge_surface --cov-report=term-missing --cov-fail-under=85
python benchmarks/runner.py
```

The coverage gate is 85%. Do not lower it to make a PR pass; add the missing test.

## What a good change looks like

- **Smallest complete change.** Touch the shared code once rather than patching call sites. Keep the existing layer boundaries.
- **No fake functionality.** Do not return `PASS` when a check cannot run; return `UNKNOWN` and report it. Do not weaken a test or a benchmark label to make a result look better.
- **Tests for new logic.** A parser branch, a rule, a state transition, or a path check needs a focused test. Use the existing fixtures and style in `tests/`.
- **Deterministic evidence.** Extraction and serialization must stay byte-for-byte stable for the same source. Do not add timestamps to serialized output.
- **Honest docs.** If something is not verified (for example, a live model run), say so in `README.md` and `docs/CLAIMS.md`.

## Rule changes

Rule results are tri-state (`PASS` / `FAIL` / `UNKNOWN`). A rule that targets a missing function fails by default; use `required: false` only when absence is intentional. Behavioural rules must remain refused for untrusted snippets; changes to the isolation controls need a threat-model note in `SECURITY.md`.

## Benchmarks

When you add a rule or change extraction, run the controlled benchmark and the external benchmark. If a label changes, explain why in the PR. External targets are pinned by full commit SHA; never replace a pin with a branch or tag.

```bash
python benchmarks/runner.py
python benchmarks/external.py          # network required
python benchmarks/agent_experiment.py
python benchmarks/perf.py
```

## Commit messages

Use a short imperative subject. Conventional Commits (`fix:`, `feat:`, `docs:`, `test:`, `chore:`) are welcome but not enforced.

## Reporting security issues

Do not open a public issue with exploit details. See `SECURITY.md`.
