# Changelog

All notable changes to this project are documented here. The format follows Keep a Changelog; versions follow Semantic Versioning.

## [0.3.1] — 2026-10-22

Follow-up correctness release. Verification now compares independent findings, so a new violation is never hidden by older debt under the same rule.

### Fixed

- Rules that already failed no longer mask a new violation. Findings are matched by `(canonical_path, semantic_key)`, not by the rule's aggregate outcome.
- Stable finding keys exclude line numbers, so moving or reformatting an existing violation does not make it "introduced". File renames map the after path to the old path; a renamed function gets a new key and is treated as introduced (fail-closed).
- All built-in rules collect every violation, including multiple functions, duplicate function names, nested definitions, module-level calls, multiple imports, and multiple findings per file. A cross-file deduplication bug in the import, forbidden-call, and orphaned-call rules is fixed.
- Repeated identical forbidden calls/imports and orphaned calls in one file now get deterministic occurrence suffixes (`#1`, `#2`, ...), so adding another target is introduced rather than hidden behind the first. Counters are per file, so duplicate keys cannot shift across files.
- Parse policy is explicit: a new parse error in a changed file is an introduced finding and blocks under `warn` and `ignore`; a pre-existing error outside a rule's scope is diagnostic only; a pre-existing error inside a rule's scope makes that rule `UNKNOWN`. Global-scope rules can still be indeterminate on any pre-existing error, which is documented fail-closed behaviour.
- `unknown_policy="ignore"` now clears unknown findings from the approval decision while keeping `rule_results` and `parse_errors` visible.
- Behavioural failures use the stable key `behavior::<rule_id>`.

### Added

- `Violation` is a public export; `RuleResult.violations` and per-rule violation counts are available through the API and JSON report.
- `benchmarks/LIVE_LLM.md` defines a reproducible live-LLM experiment (baseline vs verifier loop, held-out tasks, independent hidden tests, recorded failures). It has not been run and reports no result.
- `tests/test_violation_level.py` covers same-file and cross-file old+new violations, duplicate calls/imports, `require_call` old+new, repaired-old+new, unchanged debt, file rename, function rename, module scope, duplicate functions, annotations, and mutable defaults.
- `tests/test_perf.py` covers the nearest-rank p95 calculation.
- CLI tests for per-finding JSON, malformed input, invalid configs, unsupported files, partial extraction, and all exit codes.
- Controlled benchmark expanded from 17 to 23 scenarios; CI now runs `pip-audit --skip-editable`.

### Changed

- Test count: 167 → 197. Statement coverage: 87.32% → 89.99%; CLI module 70% → 95%.
- Controlled benchmark: 23 scenarios, 15 TP, 8 TN, 0 FP/FN/unknown/incomplete.
- `benchmarks/perf.py` now reports nearest-rank p95 and records the command, output path, platform, machine, processor, CPU count, and Python version/implementation in `perf.json`.
- Behavioural-rule evidence no longer embeds random staging paths, so benchmark reports are stable across runs.
- Agent experiment: baseline 8/23 safe → 23/23 with the loop; average overhead 28.1 ms.
- GitHub Actions updated to `actions/checkout@v7`, `actions/setup-python@v7`, and `actions/upload-artifact@v7`.
- Version: 0.3.0 → 0.3.1.

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
