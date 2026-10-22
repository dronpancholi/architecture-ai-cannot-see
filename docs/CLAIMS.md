# Claim → Evidence Matrix

Every public claim should point at code, a test, or a recorded result. "Verified" means the command was run in this working tree and its output/exit code was inspected. "Not claimed" means exactly that.

| Claim | Evidence | Status |
|---|---|---|
| Parses Python into a typed, serializable Knowledge Surface | `src/knowledge_surface/extractors/python_ast.py`, `representation/knowledge_surface.py`; `tests/test_extractors.py`, `test_representation.py`, `test_knowledge_surface.py` | Verified |
| Patches are applied to a real base checkout, not reconstructed from hunk lines | `verification/change.py`; `tests/test_paths_and_patch.py` | Verified |
| Paths from diffs/models cannot escape the repository root | `paths.py`; `tests/test_paths_and_patch.py`, `test_sandbox.py`, `test_agent_loop.py` | Verified |
| Verification is tri-state; unknown never counts as a pass | `verification/engine.py`, `rules.py`; `tests/test_tristate.py` | Verified |
| A new violation is never hidden by existing debt under the same rule | Per-finding `(path, key)` matching in `verification/engine.py`; `tests/test_violation_level.py`, `tests/test_cli.py` | Verified |
| Unchanged pre-existing findings do not block a scoped, unrelated change | `verification/engine.py`; `tests/test_tristate.py`, `test_violation_level.py` | Verified with documented exceptions for global-scope rules and parse errors |
| Parse policy is explicit: new errors block; scoped rules can be complete despite unrelated pre-existing errors | `verification/engine.py`; `tests/test_tristate.py` | Verified |
| `RequireCallRule` handles owner scoping, nested scopes, dominance, async, and missing targets | `verification/rules.py`; `tests/test_require_call.py` | Verified |
| Behavioral rules are bounded and untrusted snippets are refused by default | `verification/sandbox.py`; `tests/test_sandbox.py` | Verified |
| Behavioral execution is process isolation, **not** a security sandbox | `sandbox.py` docstring, `SECURITY.md`, `docs/VERIFICATION.md` | Documented limit |
| External benchmark uses exact pinned SHAs and verifies HEAD | `benchmarks/external.py`; `tests/test_benchmark_pins.py`; `benchmarks/external.json` target commits | Verified |
| Controlled benchmark: 23 scenarios, 15 TP, 8 TN, 0 FP/FN, 0 unknown/incomplete | `benchmarks/RESULTS.md`, `benchmarks/results.json`; reproduced with `python benchmarks/runner.py` | Verified |
| External benchmark: 10 scenarios over 2 pinned repositories, 6 TP, 4 TN, 0 FP/FN/unknown, tool 0.3.1 | `benchmarks/EXTERNAL.md`, `benchmarks/external.json` | Verified locally at pinned commits |
| Agent loop improves safe-change rate from 8/23 to 23/23 on the labelled scenarios | `benchmarks/EVIDENCE.md`; `python benchmarks/agent_experiment.py` | Verified with a deterministic scripted agent |
| Agent loop overhead is tens of milliseconds per verification | `benchmarks/EVIDENCE.md` (latest average 30.2 ms on one host) | Verified, host-dependent |
| The loop is proven with a live LLM | — | **Not claimed.** Only a deterministic `ScriptedAgent` was measured. `LLMAgent` validates/bounds prompts but was not run against a live model. |
| Test suite: 193 tests, 89.95% statement coverage; CLI module 95% | `python -m pytest --cov=knowledge_surface --cov-report=term` in `.venv` | Verified |
| Lint is clean | `ruff check .` | Verified |
| Extraction is deterministic | serialization omits timestamps/duration; `tests/test_extractors.py::test_build_is_deterministic`, `test_representation.py::test_serialization_is_sorted_and_stable` | Verified |
| Local performance baseline | `benchmarks/perf.py`, `benchmarks/perf.json` (latest 5-iteration run: extractor 43.69 ms, full build 155.24 ms, verify 6.52 ms, sandbox 27.26 ms median; cold build 459.11 ms, 9.34 MB peak, 29 files, 423 entities on Python 3.14.6) | Verified on one host; not a competitive benchmark |
| CI runs lint, tests, coverage gate, controlled benchmark, wheel smoke test, and `pip-audit` | `.github/workflows/ci.yml`; local `pip-audit --skip-editable` reported no known vulnerabilities | Local audit verified; remote run for 0.3.1 recorded after push |
| External benchmark runs weekly/manually | `.github/workflows/external.yml`; local pinned run passed | Local run verified; scheduled remote run remains unverified |
| General superiority over other tools | — | **Not claimed.** The benchmark is controlled and the external set is two repositories. |
| A literal "10/10" quality score | — | **Not claimed.** See remaining gaps in `AUDIT.md`. |

## Reproducing

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e ".[dev]" build
.venv/bin/python -m pytest --cov=knowledge_surface --cov-report=term-missing
ruff check .
.venv/bin/python benchmarks/runner.py
.venv/bin/python benchmarks/external.py
.venv/bin/python benchmarks/agent_experiment.py
.venv/bin/python benchmarks/perf.py
.venv/bin/pip-audit --skip-editable
```
