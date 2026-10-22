# Engineering Audit — Knowledge Surface

Date: 2026-10-22
Baseline commit: `5adfea4`
0.3.0 implementation commit: `c4c0e26`
0.3.1 follow-up base: `20a3251f86b51ade38a9690b7b97bd7ea6716785`
0.3.1 implementation commit: `b1700c6ea595b51c77b96023ea8ec7db2a538d89`
0.3.1 release-readiness follow-up commit: `0472f0c`
Repository: https://github.com/dronpancholi/architecture-ai-cannot-see
Branch: `main`
Baseline tests: 36 passed; working tree clean at audit start.

This report records what was inspected, changed, executed, and **not** verified. It does not claim a literal 10/10.

## 0. Follow-up audit (0.3.1)

The 0.3.0 audit below is retained as history. The follow-up found that comparing rules only by aggregate `PASS`/`FAIL` could hide a new violation whenever the same rule already failed. It also found that independent findings could collapse across files and that the parse/completeness policy was underspecified.

| # | Follow-up finding | Fix |
|---|---|---|
| F-1 | A rule that failed before and after was classified wholesale as pre-existing, so a new forbidden import or a newly failing function was hidden by old debt. | Per-finding matching by `(canonical_path, semantic_key)`. Only matching old findings are pre-existing; unmatched after findings are introduced. |
| F-2 | Stable identity used line numbers, so an unrelated line shift could turn debt into a "new" finding. | Keys exclude line numbers. File renames canonicalise the after path back to the old path. Function renames get a new key and fail closed (introduced). |
| F-3 | Import, forbidden-call, and orphaned-call collection deduplicated by key across files, so the same violation in a second file disappeared. | Deduplicate by `(path, key)`. |
| F-4 | Parse-error policy was implicit: every parse error made the report incomplete and the global block/warn/ignore switch applied uniformly. | New changed-file parse error is an introduced finding and always blocks; pre-existing unrelated error is diagnostic; pre-existing scoped error makes that rule `UNKNOWN`; global rules remain fail-closed. |
| F-5 | CLI coverage was 70% and malformed-input, unsupported-file, and per-finding JSON paths were thin. | Expanded CLI tests to 95% module coverage and added per-finding API/CLI regressions. |
| F-6 | A second identical forbidden call or import in the same file reused the first finding's key, so adding it was hidden as pre-existing. | Deterministic occurrence suffixes (`#1`, `#2`, ...); the first target keeps the unsuffixed key. Counters are per file, so cross-file keys cannot shift. |
| F-7 | The performance report's p95 used the wrong index for small samples (five samples reported the fourth value, not the maximum) and did not record the command, output path, or environment. | Nearest-rank p95; `perf.json` now records command, output, platform, machine, processor, CPU count, and Python version/implementation. |
| F-8 | Behavioural-rule evidence included random staging paths, so benchmark reports changed on every run. | Staging paths are replaced with `<candidate>` in evidence (longest path first); `tests/test_sandbox.py` covers the stable form. |

The follow-up adds `tests/test_violation_level.py`, expands `tests/test_tristate.py` and `tests/test_cli.py`, exports `Violation`, adds per-rule violation counts, and updates CI with `pip-audit`. It does not change the historical finding descriptions in sections 1–6. A second pass adds duplicate-occurrence keys and the `perf.py` metadata/p95 fix.

## 1. Audit findings

### P0 — correctness / security

| # | Finding | Reproduction | Fix |
|---|---|---|---|
| P0-1 | `ChangeSet.from_patch()` concatenated only hunk lines, so the candidate tree was missing all unchanged source. Structural rules evaluated a truncated file. | Patch one line of a 100-line file; `after_tree` contained only the hunk. | Strict unified-diff applier against a real base checkout; multi-file/multi-hunk, add/delete/rename/copy, quoted paths, no-newline markers; reject patches that do not apply. |
| P0-2 | No path validation. `FileChange.path` could be absolute, `../`, or symlink-escaping; the verifier wrote it. | `FileChange(path="../../tmp/x.py", ...)` wrote outside the temp root. | Central `paths.py` normalization/containment checks after symlink resolution; every change set and sandbox tree is validated. |
| P0-3 | Tri-state missing. `RuleResult` was boolean; `UNKNOWN` became `passed=False` and was classified as pre-existing debt. Parse failures were dropped. | A baseline rule that could not run turned a new violation into "pre-existing". | `Outcome` enum; `unknown` report section; `--unknown-policy block|warn|ignore`; parse errors are diagnostics; unknown never becomes pre-existing. |
| P0-4 | `RequireCallRule` passed when the target function was absent; nested-function calls satisfied the rule; ordering was line-number only. | Delete `delete_account`; rule passed. Add a nested helper calling `authorize`; rule passed. | Missing target fails by default (`required: false` opts out); nested scopes pruned; conservative dominance; async support; owner scoping. |
| P0-5 | Behavioural rules inherited the full environment, buffered unbounded output, and killed only the direct child. Docs implied isolation. | Snippet printed gigabytes, spawned a child, or read environment secrets. | Minimal env, `-E -s`, new process group + `SIGKILL`, POSIX rlimits, 16 KiB output bound, untrusted refusal by default. Documented as process isolation, not a sandbox. |
| P0-6 | External benchmark declared pins but cloned default branches; `--path` applied every target to one checkout. | Upstream default-branch change silently changed results. | Fetch and check out the exact SHA, verify `git rev-parse HEAD`, record metadata; `--path` requires `--target`; unknown/incomplete results fail. |

### P1 — reproducibility / agent / representation

| # | Finding | Fix |
|---|---|---|
| P1-1 | Loop returned an unverified revision after budget exhaustion. | Terminal-state enum (`APPROVED`, `REJECTED`, `EXHAUSTED`, `AGENT_ERROR`, `VERIFIER_ERROR`, `INDETERMINATE`); final candidate is always the last verified candidate. |
| P1-2 | LLM adapter sent the whole repo, ignored its `root` when reading `before`, and accepted unsafe/duplicate paths. | Bounded/focused context, secret-assignment redaction, JSON/schema validation, unsafe/duplicate path rejection, rename/delete support, fresh `before` from the current root. |
| P1-3 | Knowledge Surface had no schema version, no duplicate-ID checks, non-deterministic serialization. | Schema version `1`, validation, duplicate-ID rejection, sorted output, load checks; function/class IDs include definition line. |
| P1-4 | Extractor followed all dirs/symlinks, silently dropped parse failures, no diagnostics. | Exclusion set, symlink containment, file-count/size caps, `UNKNOWN` parse-failure modules, deterministic diagnostics. |
| P1-5 | Drift duplicate detection only inspected `after`; a naming-divergence variable was wrong. | Before/after comparison, pre-existing vs. new duplicates, relationship/provenance/confidence checks, partial-extraction evidence. |
| P1-6 | CLI returned 0 for input errors, exposed tracebacks, and `build` skipped deep extractors. | Exit-code contract, input-error handling, full pipeline, JSON output. |
| P1-7 | No CI, security policy, contribution surface, or claim matrix. | CI + scheduled external workflow, `SECURITY.md`, `CONTRIBUTING.md`, `CHANGELOG.md`, `ROADMAP.md`, templates, `docs/CLAIMS.md`. |
| P1-8 | No performance data. | `benchmarks/perf.py` + `perf.json`; README/docs record the baseline. |

## 2. Implementation summary

Changed or added:

- `verification/change.py` — strict patch application; `parse_python` returns `(tree, error)`; `ChangeSet.validate/after_tree/before_tree`.
- `verification/rules.py` — tri-state results, missing-target flag, nested-scope pruning, conditional dominance, async functions, owner scoping, required decorator, allowlist reasons, untrusted behavioural refusal.
- `verification/engine.py` — introduced/pre-existing/unknown/improvement classification, unknown policy, parse errors, deterministic ordering, path validation.
- `verification/sandbox.py` — bounded, process-group-isolated behavioural execution.
- `verification/feedback.py` — unknown, parse-error, improvement, and suppression feedback (JSON + Markdown).
- `paths.py` — normalize/resolve/contain, safe write, tree walk with exclusions, symlink containment, size caps.
- `agent/loop.py`, `agent/llm_adapter.py` — terminal states, last-verified final candidate, bounded redacted context, validated responses.
- `benchmarks/external.py`, `benchmarks/runner.py`, `benchmarks/perf.py` — exact pins and HEAD verification, unknown/incomplete accounting, local performance baseline.
- `representation/` — schema version, validation, deterministic serialization, code-only dependency graph.
- `extractors/python_ast.py`, `extractors/deep.py` — exclusions, parse diagnostics, package-relative imports, conservative call graph, dynamic imports, framework capabilities.
- `drift/detector.py` — before/after drift findings with evidence, confidence, suggestions.
- `cli.py` — exit codes `0/1/2/3`, root-aware patch parsing, unknown policy, JSON report.
- Tests, docs, workflows, and project metadata.

## 3. Test report

Command (`.venv`, Python 3.14.6):

```text
.venv/bin/python -m pytest --cov=knowledge_surface --cov-report=term --cov-fail-under=85
197 passed in 4.19s
TOTAL 2637 statements, 264 missed, 89.99% coverage
Required test coverage of 85% reached.
```

`ruff check .` → `All checks passed!`

New test files and what they cover:

| File | Focus |
|---|---|
| `test_paths_and_patch.py` | multi-file/hunk patches, renames, quoted paths, traversal/symlink rejection |
| `test_tristate.py` | full before/after matrix, unknown policy, parse/completeness policy, ordering |
| `test_violation_level.py` | per-finding matching, old+new violations in one file and across files, renames, duplicate functions, module scope, duplicate calls/imports |
| `test_require_call.py` | owner scope, nested scope pruning, dominance, async, missing target |
| `test_sandbox.py` | untrusted refusal, timeout, process-group kill, output bound, minimal env, stable evidence |
| `test_agent_loop.py` | every terminal state, repeated revision, stale `before`, prompt bounds, path/JSON validation |
| `test_representation.py` | schema version, duplicate IDs, determinism, code-only graph |
| `test_extractors.py` | exclusions, parse failures, relative imports, ambiguity, dynamic imports, frameworks |
| `test_cli.py` | exit codes 0/1/2/3, per-finding JSON, malformed inputs, unsupported files, drift gate |
| `test_benchmark_pins.py` | exact checkout, HEAD verification, anchor failure, target selection |
| `test_perf.py` | nearest-rank p95 used by the performance report |

Remote CI (GitHub Actions run `39816473583`, commit `0472f0c`) reports `success`; every step of the Python 3.11, 3.12, and 3.13 jobs and the `dependency audit` job completed successfully. The earlier run `39797461409` covers the previous docs-only commit. CLI coverage is 95%.

## 4. Security report

Verified controls:

- **Path containment:** absolute paths, `..`, NUL bytes, backslashes, and symlink escapes are rejected before writes. Tests cover diffs, sandbox staging, and model responses.
- **Patch trust boundary:** modified/deleted/renamed files require a base checkout; truncated or context-mismatched patches raise `PatchError` instead of reconstructing.
- **Behavioural execution:** minimal environment (`-E -s`), wall-clock timeout, process-group `SIGKILL`, POSIX rlimits, 16 KiB combined output, temp tree. Untrusted snippets are refused unless explicitly trusted.
- **Model input:** prompt context is bounded and focused; common secret assignments are redacted; response JSON and paths are validated.
- **No credentials** are stored in the repository; no obvious secret patterns were found in the diff.

- **Dependency audit:** CI runs `pip-audit --skip-editable`; the local 0.3.1 environment reported no known vulnerabilities.
- No automated live-LLM evaluation is claimed.

Residual risk, stated plainly:

- Behavioural execution is **process isolation, not a security sandbox**. A trusted snippet can still harm the host. Use a container/VM for hostile code.
- Prompt redaction is a heuristic, not a guarantee against a hostile model provider.
- A dependency audit reports known advisories at scan time; it is not a proof that dependencies are vulnerability-free.
- The scheduled external workflow has not been run remotely in this audit; the local pinned run passed.

## 5. Benchmark report

Controlled benchmark — 23 labelled scenarios:

```json
{"scenarios": 23, "tp": 15, "fp": 0, "tn": 8, "fn": 0,
 "unknown": 0, "incomplete": 0,
 "precision": 1.0, "recall": 1.0, "f1": 1.0,
 "accuracy": 1.0, "false_positive_rate": 0.0}
```

New scenarios cover old+new imports in one file, old+new imports across files, a renamed file with preserved debt, an unrelated pre-existing parse error, and `require_call` old+new plus repaired-old+new.

External benchmark — 10 scenarios, 2 exact-pinned repositories:

| Target | Commit | Scenarios | TP | TN | FP | FN | Unknown |
|---|---|---|---|---|---|---|---|
| `pallets/itsdangerous` | `672971d66a2ef9f85151e53283113f33d642dabd` | 5 | 3 | 2 | 0 | 0 | 0 |
| `psf/requests` | `611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60` | 5 | 3 | 2 | 0 | 0 | 0 |

Each checkout was fetched at the declared SHA and `git rev-parse HEAD` was verified. `benchmarks/EXTERNAL.md` records tool version 0.3.1; the pinned external run was repeated after the follow-up.

Agent experiment: baseline commits 8/23 safe changes; the verified loop commits 23/23. Average iterations 1.0 → 1.7. Latest average verification overhead 28.1 ms on one host. The revision policy is deterministic; this measures gating and convergence, not live-LLM repair quality.

Scope caveat: 23 controlled scenarios and 10 external scenarios are evidence, not proof of general superiority. The controlled fixtures were designed alongside the rules; the external set is two repositories.

## 6. Performance report

Command: `.venv/bin/python benchmarks/perf.py --iterations 5`
Output: `benchmarks/perf.json` (regenerated after the final source change).
Environment: Python 3.14.6 (CPython), macOS-27.2-arm64-arm-64bit-Mach-O, arm64, 10 CPUs, one host.

| Operation | Median | p95 | Min | Max |
|---|---|---|---|---|
| Extractor only | 45.72 ms | 58.41 ms | 42.89 ms | 58.41 ms |
| Full build | 158.49 ms | 167.10 ms | 152.99 ms | 167.10 ms |
| Verify safe change | 6.59 ms | 9.55 ms | 6.51 ms | 9.55 ms |
| Sandbox check | 23.53 ms | 40.32 ms | 23.25 ms | 40.32 ms |

Cold full build: 466.38 ms, 9.39 MB peak (`tracemalloc`), 29 files, 424 entities, 1032 relationships. p95 is nearest-rank; with five samples it equals the maximum. This is a regression baseline, not a comparison with other tools.

## 7. API / compatibility report

- Version: `0.2.0` → `0.3.0` → `0.3.1`.
- New public exports: `Outcome`, `Finding`, `Violation`, `RequiredDecoratorRule`, `SCHEMA_VERSION`, `SchemaError`, `LoopState`, `LLMAgent`, `AgentError`, `Agent`.
- `RuleResult.passed` remains for compatibility; `RuleResult.outcome` is authoritative. `UNKNOWN` is not `PASS`. `RuleResult.violations` is additive and lists every finding.
- `Finding` adds a stable `key`; `VerificationReport` adds `unknown`, `improvements`, `parse_errors`, `rule_results`, `complete`, `unknown_policy`. `rule_results` records before/after outcomes and violation counts.
- Verification matches findings by `(canonical_path, key)`. `unknown_policy="ignore"` clears rule-level unknown findings from the approval decision but leaves `rule_results` and `parse_errors` visible.
- `ChangeSet.from_patch(patch)` now requires a `root` for modified/deleted/renamed files. This is intentionally breaking: the previous behaviour produced an incomplete candidate. Pure-add patches still work without a root.
- Untrusted `BehavioralRule` results are now `UNKNOWN` instead of executed.
- Schema documents carry `schema_version: 1`; loading accepts missing version as `0` and rejects newer versions.
- CLI now uses exit codes `0/1/2/3`; `build` runs the full pipeline; `verify` accepts `--unknown-policy` and `--json-out`.

## 8. Remaining gaps

1. No live-LLM evaluation. The loop is proven only with a deterministic `ScriptedAgent`; `benchmarks/LIVE_LLM.md` defines the held-out, independent-test experiment but it has **not** been run.
2. The scheduled external workflow has not been run remotely; the local pinned run passed. The controlled CI workflow for `b1700c6` passed as run `39794512119`.
3. External evidence is 10 scenarios over 2 repositories.
4. Behavioural rules are not a security sandbox.
5. Python is the only supported language.
6. Function renames are treated as introduced (fail-closed); the engine does not attempt semantic rename matching.
7. Performance was measured on one macOS host, not across platforms; `perf.json` records that environment.
8. `pip-audit` is advisory-data dependent and runs in CI; it is not a proof of absence.

## 9. Acceptance gates

| Gate | Status | Evidence |
|---|---|---|
| A. Source integrity | **Pass** | Baseline `5adfea4` recorded; working tree inspected before edits; no history rewrite or force push; `git diff --check` clean; no unrelated deletion. |
| B. Security | **Pass with residual risk** | Path containment tests, patch base requirement, sandbox controls, untrusted refusal, `SECURITY.md`; residual risk documented in §4. |
| C. Verification correctness | **Pass** | 197 tests; per-finding old+new, duplicate-occurrence, and sandbox-evidence regressions; controlled 0 FP/FN; external 0 FP/FN with exact pins. |
| D. Reproducibility | **Pass** | Deterministic extraction/serialization; exact SHA pins + HEAD verification; wheel build/install smoke test; GitHub Actions CI run `39816473583` reports success for 3.11, 3.12, 3.13, and the dependency audit. |
| E. Evidence | **Pass, bounded** | `RESULTS.md`, `EXTERNAL.md`, `EVIDENCE.md`, `perf.json`, `docs/CLAIMS.md`; scope caveats stated. |
| F. Hygiene | **Pass** | `ruff check .` clean; 89.99% coverage (gate 85%); `pip-audit` clean; `python -m build` produced 0.3.1 sdist/wheel; wheel installed in a fresh venv and `ks --help` ran. |
| G. Documentation | **Pass** | README, architecture, verification, claims matrix, security, contributing, changelog, roadmap, templates aligned with implementation. |
| H. Final review | **Pass** | Diff reviewed; secrets scan found no obvious credentials; final state recorded in git history. |

## 10. Evidence-based rating

| Dimension | Score | Basis |
|---|---|---|
| Verification correctness | 9.5/10 | Complete per-finding matrix, strict patches, conservative rules, 197 tests |
| Security | 8.5/10 | Strong path/patch controls; dependency audit in CI; process isolation is explicitly not a sandbox |
| Reproducibility | 9/10 | Exact pins, HEAD verification, deterministic output, wheel smoke test, verified 0.3.1 remote CI |
| Evidence quality | 8.5/10 | 23 controlled + 10 external + agent + performance evidence; small external sample |
| Test depth | 9/10 | 89.99% coverage; CLI at 95%; per-finding regressions |
| Documentation / maintainability | 9/10 | Claims matrix, limits, templates, changelog, roadmap |
| Production readiness | 6/10 | Alpha, Python-only, no live-LLM result; dependency audit exists but is advisory-only |

**Scoped overall: 8.5/10.** This is a materially stronger reference implementation than the baseline, with per-finding correctness, parse policy, dependency audit, and CLI coverage materially improved. It is **not** a production-hardened verifier and **not** a 10/10: live-model behaviour, broader external evidence, real sandboxing, and cross-platform performance remain open.

## 11. Final commands

```text
.venv/bin/ruff check .                                      # All checks passed
.venv/bin/python -m pytest --cov=... --cov-fail-under=85    # 197 passed, 89.99%
.venv/bin/python benchmarks/runner.py                       # 23 scenarios, 0 FP/FN
.venv/bin/python benchmarks/external.py                     # 10 scenarios, 0 FP/FN
.venv/bin/python benchmarks/agent_experiment.py             # 8/23 -> 23/23
.venv/bin/python benchmarks/perf.py --iterations 5           # writes benchmarks/perf.json
.venv/bin/pip-audit --skip-editable                         # no known vulnerabilities
.venv/bin/python -m build                                   # 0.3.1 sdist + wheel
# fresh venv: pip install dist/*.whl && ks --help             # passed
# GitHub Actions: CI run 39786564650                            # prior run, 3.11/3.12/3.13
# 0.3.1 remote run: 39816473583 (all steps of 3.11/3.12/3.13 + audit passed)
```
