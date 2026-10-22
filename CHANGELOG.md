# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog; versions follow Semantic Versioning.

## [0.3.0] — 2026-10-22

Security and correctness release. The verifier no longer guesses when it cannot see the whole candidate file, and "unknown" is no longer silently treated as "passed".

### Fixed

- Patches are applied to a real base checkout instead of concatenating visible hunk lines. Multi-file/multi-hunk diffs, adds, deletes, renames, copies, quoted paths, and `\ No newline at end of file` are handled. Patches that do not apply are rejected.
- Path traversal, absolute paths, NUL bytes, and symlink escapes are rejected before any filesystem write (`paths.py`).
- Results are tri-state. `UNKNOWN` is a first-class report section, never a pass, and never "pre-existing". `--unknown-policy block|warn|ignore` controls the gate; `block` is the default.
- Parse failures are reported as diagnostics and make affected rules `UNKNOWN`.
- `RequireCallRule` now fails when its target function is absent (unless `required: false`), ignores calls in nested scopes, requires the guard to dominate the sensitive call, supports async functions, and scopes by owner class.
- `RequiredDecoratorRule` added.
- Behavioural rules run with a minimal environment, process-group `SIGKILL` on timeout, POSIX rlimits, and bounded output. Untrusted snippets are refused unless explicitly allowed. This is process isolation, not a security sandbox.
- External benchmark fetches the exact pinned commit, verifies `git rev-parse HEAD`, records metadata, and fails on unknown/incomplete results. `--path` now requires an explicit `--target`.
- The agent loop has terminal states (`APPROVED`, `REJECTED`, `EXHAUSTED`, `AGENT_ERROR`, `VERIFIER_ERROR`, `INDETERMINATE`); the final candidate is always the last verified candidate.
- The LLM adapter reads `before` from the current root, bounds and focuses context, redacts common secret assignments, validates JSON/schema, and rejects unsafe or duplicate paths.
- Extraction excludes vendored/cache directories, does not follow symlinks outside the root, caps file count/size, resolves package-relative imports, and reports parse failures as `UNKNOWN` modules.
- Call-graph edges are conservative: ambiguous, locally shadowed, or dynamically unresolvable targets are skipped and counted rather than guessed.
- Drift detection compares before and after, distinguishes pre-existing from new duplicates, and reports partial extraction.
- Representation has a schema version, duplicate-ID validation, and deterministic serialization. Function/class IDs include their definition line to disambiguate duplicate names.
- CLI has a documented exit-code contract (`0` success/approved, `1` policy rejection, `2` input error, `3` indeterminate) and `--json-out`.

### Added

- `tests/test_paths_and_patch.py`, `test_tristate.py`, `test_require_call.py`, `test_sandbox.py`, `test_agent_loop.py`, `test_representation.py`, `test_extractors.py`, `test_cli.py`, `test_benchmark_pins.py`.
- `benchmarks/perf.py` and `benchmarks/perf.json`.
- CI workflow (Python 3.11–3.13, lint, coverage gate, benchmark gate, wheel smoke test) and a scheduled/manual pinned external-benchmark workflow.
- `SECURITY.md`, `CONTRIBUTING.md`, `ROADMAP.md`, `docs/CLAIMS.md`, issue and pull-request templates.

### Changed

- Test count: 36 → 167. Statement coverage: 87% (`pytest-cov`).
- Version: 0.2.0 → 0.3.0.
- README limits and evidence claims now match the recorded results.

## [0.2.0] — 2026-10-21

- Semantic verification engine with before/after rule evaluation and regression-only blocking.
- Controlled benchmark (17 scenarios) and external benchmark (`pallets/itsdangerous`).
- Agent feedback loop and baseline experiment.
- CLI: `build`, `inspect`, `query`, `check`, `verify`, `drift`, `report`.

## [0.1.0] — 2026-10-20

- Initial Knowledge Surface representation, Python AST extractor, invariant registry, consistency checker, and drift detector.
