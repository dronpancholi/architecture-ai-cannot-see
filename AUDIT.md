# Engineering Audit — Knowledge Surface

Date: 2026-10-22
Baseline commit: `5adfea4`
Baseline tests: 36 passed (`python3 -m pytest -q`, exit 0)
Working tree at audit start: clean
Remote: `origin` → https://github.com/dronpancholi/architecture-ai-cannot-see.git
Default branch: `main`

## Findings

### P0 — correctness / security

| # | Finding | Reproduction | Fix |
|---|---|---|---|
| P0-1 | `ChangeSet.from_patch()` concatenates only hunk lines, so the candidate tree is missing all unchanged source. Structural rules evaluate a truncated file. | Verify a patch touching one line of a 100-line file; `after_tree` contains only the hunk. | Rewrite parser as a strict unified-diff applier against the base checkout; reject patches that do not apply. |
| P0-2 | No path validation. `FileChange.path` can be absolute, `../`, or symlink-escaping; `_build_from_tree` and `_run_behavioral` write it. | `FileChange(path="../../tmp/x.py", after="...")` writes outside the temp root. | Central `paths.py` with normalize/resolve/containment checks; validate every change set before use. |
| P0-3 | Tri-state missing. `RuleResult.passed` is boolean; `UNKNOWN` is encoded as `passed=False` then classified as pre-existing debt. Parse failures are dropped by `after_asts()`. | A baseline rule that cannot be evaluated turns a new violation into “pre-existing”. | Add `Outcome` enum; add `unknown` report bucket and policy; parse errors reported and classified. |
| P0-4 | `RequireCallRule` silently passes when the target function is absent; `ast.walk` counts calls in nested functions; ordering is line-number only. | Delete `delete_account`; rule passes. Add nested helper that calls `authorize`; rule passes. | Require target by default; prune nested scopes; conservative block-dominance check. |
| P0-5 | Behavioural rules inherit the full environment, buffer unbounded output, and only kill the direct child on timeout. Docs imply isolation. | Snippet prints gigabytes / spawns child / reads env secrets. | Minimal env, `-I`, new session, process-group kill, rlimits, bounded output, explicit trust flag, refuse untrusted by default. |
| P0-6 | External benchmark declares pins but clones the default branch; `--path` applies every target to one checkout. | Change upstream default branch; results silently change. | Fetch and check out the exact SHA, verify HEAD, record metadata, explicit `--path`/`--target` pairing. |

### P1 — reproducibility / agent / representation

| # | Finding | Fix |
|---|---|---|
| P1-1 | Loop returns an unverified revision after budget exhaustion. | Terminal-state enum; final candidate is always the last verified one. |
| P1-2 | LLM adapter sends the whole repo, ignores its `root` argument when reading `before`, and accepts unsafe/duplicate paths. | Bounded context, focus files, path validation, schema errors, stale-content refresh. |
| P1-3 | Knowledge Surface has no schema version, no duplicate-ID checks, non-deterministic serialization. | Schema version, validation, sorted output, load checks. |
| P1-4 | Extractor follows all dirs/symlinks, silently drops parse failures, no diagnostics. | Exclusion set, symlink containment, parse-failure diagnostics, size cap. |
| P1-5 | Drift duplicate detection only inspects `after`; variable leak in naming divergence. | Before/after comparison, kind-aware matching, ambiguous matches reported. |
| P1-6 | CLI returns 0 for input errors, exposes tracebacks, and `build` skips deep extractors. | Exit-code contract, error handling, full pipeline, JSON output. |
| P1-7 | No CI, no security policy, no contribution surface, no claim matrix. | Workflow, SECURITY/CONTRIBUTING/CHANGELOG/ROADMAP, templates, claim matrix. |
| P1-8 | No performance data. | `benchmarks/perf.py` + recorded `PERF.md`. |

### P2 — maintainability / docs

- README overstates “100%” without sample-size caveats (partly corrected).
- Author metadata generic; whitepaper author unknown.
- No changelog, roadmap, issue templates.
- Version 0.2.0; bump after fixes.

## Baseline commands

```
python3 -m pytest -q                  # 36 passed
python3 benchmarks/runner.py          # 17 scenarios, 100% precision/recall
python3 benchmarks/external.py        # 10 scenarios, 100% (default branches, not pins)
python3 benchmarks/agent_experiment.py# baseline 6/17 safe, loop 17/17
```

## Acceptance gates

A source integrity, B security, C verification correctness, D reproducibility,
E evidence, F hygiene, G docs, H final review — status recorded at the end of
this file after implementation.
