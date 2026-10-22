# Engineering Audit — Knowledge Surface

Date: 2026-10-22
Baseline commit: `5adfea4`
Implementation commit: `c4c0e26`
Repository: https://github.com/dronpancholi/architecture-ai-cannot-see
Branch: `main`
Baseline tests: 36 passed; working tree clean at audit start.

This report records what was inspected, changed, executed, and **not** verified. It does not claim a literal 10/10.

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
167 passed in 3.86s
TOTAL 2516 statements, 319 missed, 87.32% coverage
Required test coverage of 85% reached.
```

`ruff check .` → `All checks passed!`

New test files and what they cover:

| File | Focus |
|---|---|
| `test_paths_and_patch.py` | multi-file/hunk patches, renames, quoted paths, traversal/symlink rejection |
| `test_tristate.py` | full before/after matrix, unknown policy, parse errors, ordering |
| `test_require_call.py` | owner scope, nested scope pruning, dominance, async, missing target |
| `test_sandbox.py` | untrusted refusal, timeout, process-group kill, output bound, minimal env |
| `test_agent_loop.py` | every terminal state, repeated revision, stale `before`, prompt bounds, path/JSON validation |
| `test_representation.py` | schema version, duplicate IDs, determinism, code-only graph |
| `test_extractors.py` | exclusions, parse failures, relative imports, ambiguity, dynamic imports, frameworks |
| `test_cli.py` | exit codes 0/1/2/3, JSON output, input errors, drift gate |
| `test_benchmark_pins.py` | exact checkout, HEAD verification, anchor failure, target selection |

Remote CI (GitHub Actions run `39786564650`) passed on Python 3.11, 3.12, and 3.13. CLI coverage is 70%, the lowest module.

## 4. Security report

Verified controls:

- **Path containment:** absolute paths, `..`, NUL bytes, backslashes, and symlink escapes are rejected before writes. Tests cover diffs, sandbox staging, and model responses.
- **Patch trust boundary:** modified/deleted/renamed files require a base checkout; truncated or context-mismatched patches raise `PatchError` instead of reconstructing.
- **Behavioural execution:** minimal environment (`-E -s`), wall-clock timeout, process-group `SIGKILL`, POSIX rlimits, 16 KiB combined output, temp tree. Untrusted snippets are refused unless explicitly trusted.
- **Model input:** prompt context is bounded and focused; common secret assignments are redacted; response JSON and paths are validated.
- **No credentials** are stored in the repository; no obvious secret patterns were found in the diff.

Residual risk, stated plainly:

- Behavioural execution is **process isolation, not a security sandbox**. A trusted snippet can still harm the host. Use a container/VM for hostile code.
- Prompt redaction is a heuristic, not a guarantee against a hostile model provider.
- No automated dependency-audit gate yet (`pip-audit` is on the roadmap).
- CI remote execution and GitHub token permissions were not verified; a token without `workflow` scope can block workflow pushes.

## 5. Benchmark report

Controlled benchmark — 17 labelled scenarios:

```json
{"scenarios": 17, "tp": 11, "fp": 0, "tn": 6, "fn": 0,
 "unknown": 0, "incomplete": 0,
 "precision": 1.0, "recall": 1.0, "f1": 1.0,
 "accuracy": 1.0, "false_positive_rate": 0.0}
```

External benchmark — 10 scenarios, 2 exact-pinned repositories:

| Target | Commit | Scenarios | TP | TN | FP | FN | Unknown |
|---|---|---|---|---|---|---|---|
| `pallets/itsdangerous` | `672971d66a2ef9f85151e53283113f33d642dabd` | 5 | 3 | 2 | 0 | 0 | 0 |
| `psf/requests` | `611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60` | 5 | 3 | 2 | 0 | 0 | 0 |

Each checkout was fetched at the declared SHA and `git rev-parse HEAD` was verified. `benchmarks/EXTERNAL.md` records tool version 0.3.0.

Agent experiment: baseline commits 6/17 safe changes; the verified loop commits 17/17. Average iterations 1.0 → 1.6. Verification overhead observed at 37.8–85.1 ms across runs (latest 60.4 ms) on one host. The revision policy is deterministic; this measures gating and convergence, not live-LLM repair quality.

Scope caveat: 17 controlled scenarios and 10 external scenarios are evidence, not proof of general superiority. The controlled fixtures were designed alongside the rules; the external set is two repositories.

## 6. Performance report

`benchmarks/perf.py --iterations 20`, Python 3.14.6, one host:

| Operation | Median | p95 | Min | Max |
|---|---|---|---|---|
| Extractor only | 105.87 ms | 221.78 ms | 91.71 ms | 459.21 ms |
| Full build | 276.73 ms | 395.33 ms | 242.96 ms | 555.49 ms |
| Verify safe change | 20.60 ms | 25.82 ms | 17.41 ms | 25.98 ms |
| Sandbox check | 78.24 ms | 84.98 ms | 44.22 ms | 86.69 ms |

Cold full build: 719.48 ms, 8.84 MB peak (`tracemalloc`), 29 files, 417 entities, 1013 relationships. Earlier runs on the same host measured extractor 70–122 ms, full build 259–324 ms, verify 13–21 ms, sandbox 44–78 ms. The numbers are a regression baseline, not a comparison with other tools.

## 7. API / compatibility report

- Version: `0.2.0` → `0.3.0`.
- New public exports: `Outcome`, `Finding`, `RequiredDecoratorRule`, `SCHEMA_VERSION`, `SchemaError`, `LoopState`, `LLMAgent`, `AgentError`, `Agent`.
- `RuleResult.passed` remains for compatibility; `RuleResult.outcome` is now authoritative. `UNKNOWN` is not `PASS`.
- `VerificationReport` adds `unknown`, `improvements`, `parse_errors`, `rule_results`, `complete`, `unknown_policy`; `approved` is false for unknown under the default `block` policy.
- `ChangeSet.from_patch(patch)` now requires a `root` for modified/deleted/renamed files. This is intentionally breaking: the previous behaviour produced an incomplete candidate. Pure-add patches still work without a root.
- Untrusted `BehavioralRule` results are now `UNKNOWN` instead of executed.
- Schema documents carry `schema_version: 1`; loading accepts missing version as `0` and rejects newer versions.
- CLI now uses exit codes `0/1/2/3`; `build` runs the full pipeline; `verify` accepts `--unknown-policy` and `--json-out`.

## 8. Remaining gaps

1. No live-LLM evaluation. The loop is proven only with a deterministic `ScriptedAgent`.
2. The scheduled external workflow has not been run remotely yet; the controlled CI workflow passed.
3. External evidence is 10 scenarios over 2 repositories.
4. Behavioural rules are not a security sandbox.
5. Python is the only supported language.
6. No dependency-audit gate.
7. CLI coverage is 70%; the weakest tested surface.
8. Performance was measured on one macOS host, not across platforms.

## 9. Acceptance gates

| Gate | Status | Evidence |
|---|---|---|
| A. Source integrity | **Pass** | Baseline `5adfea4` recorded; working tree inspected before edits; no history rewrite or force push; `git diff --check` clean; no unrelated deletion. |
| B. Security | **Pass with residual risk** | Path containment tests, patch base requirement, sandbox controls, untrusted refusal, `SECURITY.md`; residual risk documented in §4. |
| C. Verification correctness | **Pass** | 167 tests; tri-state matrix; controlled 0 FP/FN; external 0 FP/FN with exact pins. |
| D. Reproducibility | **Pass** | Deterministic extraction/serialization; exact SHA pins + HEAD verification; wheel build/install smoke test; GitHub Actions CI passed on 3.11, 3.12, and 3.13 (run `39786564650`). |
| E. Evidence | **Pass, bounded** | `RESULTS.md`, `EXTERNAL.md`, `EVIDENCE.md`, `perf.json`, `docs/CLAIMS.md`; scope caveats stated. |
| F. Hygiene | **Pass** | `ruff check .` clean; 87.32% coverage (gate 85%); `python -m build` produced 0.3.0 sdist/wheel; wheel installed in a fresh venv and `ks --help` ran. |
| G. Documentation | **Pass** | README, architecture, verification, claims matrix, security, contributing, changelog, roadmap, templates aligned with implementation. |
| H. Final review | **Pass** | Diff reviewed; secrets scan found no obvious credentials; final state recorded in git history. |

## 10. Evidence-based rating

| Dimension | Score | Basis |
|---|---|---|
| Verification correctness | 9/10 | Complete tri-state matrix, strict patches, conservative rules, 167 tests |
| Security | 8/10 | Strong path/patch controls; process isolation is explicitly not a sandbox; no dependency audit |
| Reproducibility | 9/10 | Exact pins, HEAD verification, deterministic output, wheel smoke test; remote CI unverified |
| Evidence quality | 8/10 | Controlled + external + agent + performance evidence; small external sample |
| Test depth | 8.5/10 | 87% coverage; CLI at 70% |
| Documentation / maintainability | 9/10 | Claims matrix, limits, templates, changelog, roadmap |
| Production readiness | 6/10 | Alpha, Python-only, no live-LLM or dependency-audit gate |

**Scoped overall: 8/10.** This is a materially stronger reference implementation than the baseline, with the main correctness and security traps closed and the evidence made reproducible. It is **not** a production-hardened verifier and **not** a 10/10: live-model behaviour, broader external evidence, real sandboxing, and cross-platform CI remain open.

## 11. Final commands

```text
.venv/bin/ruff check .                                      # All checks passed
.venv/bin/python -m pytest --cov=... --cov-fail-under=85    # 167 passed, 87.32%
.venv/bin/python benchmarks/runner.py                       # 17 scenarios, 0 FP/FN
.venv/bin/python benchmarks/external.py                     # 10 scenarios, 0 FP/FN
.venv/bin/python benchmarks/agent_experiment.py             # 6/17 -> 17/17
.venv/bin/python benchmarks/perf.py --iterations 20         # recorded above
.venv/bin/python -m build                                   # 0.3.0 sdist + wheel
# fresh venv: pip install dist/*.whl && ks --help             # passed
# GitHub Actions: CI run 39786564650                            # 3.11/3.12/3.13 passed
```
