# Live-LLM repair experiment — design only

**Status: not run. No live-LLM result is claimed.** This document defines a
reproducible experiment so a future run can be compared with the deterministic
scripted experiment. Without model credentials, only this protocol exists.

## Question

Does verifier feedback improve a model's ability to complete a coding task
without submitting an unsafe change, compared with the same model's one-shot
answer?

The scripted experiment in `EVIDENCE.md` answers a different question: it shows
that the loop gates and converges on a fixed repair. It is not evidence that a
live model repairs well.

## Arms

Run every task through both arms with the same model and settings:

| Arm | Behaviour |
|---|---|
| `baseline` | One proposal. No verifier feedback. Commit the first syntactically valid change set. |
| `loop` | Same model, same task. `FeedbackLoop` verifies each proposal and returns structured feedback. Max 3 verifications, then stop. |

The `loop` arm's final candidate is the last **verified** candidate; an
unverified revision is never counted as the result.

## Task set

Use a frozen, held-out set of at least 12 tasks not used to design rules or
prompts. Each task is a directory:

```text
benchmarks/live_llm/tasks/<task>/
├── repo/              # source visible to the model
├── task.json          # prompt and verifier rule config
└── tests/             # hidden tests; never included in the prompt
```

Mix four behaviour-preserving refactors, four feature/fix tasks, and four
architecture-sensitive tasks. Record a SHA-256 of every task file in the run
manifest before the first model call. Do not edit tasks during a run.

## Independent success measurement

Success is measured by the hidden test suite, not by the verifier:

1. Copy `repo/` to a fresh temporary directory.
2. Apply the returned full-file changes/renames/deletes.
3. Copy `tests/` into the temporary directory.
4. Run `python -m pytest -q tests` with a fixed timeout, in a minimal
   environment, and record exit code, stdout, stderr, and duration.
5. A task succeeds only when the hidden tests pass. A timeout or test
   collection error is a failure, not a skip.

Record verifier approval separately. A change can pass the verifier and fail
the hidden tests, or pass the hidden tests and violate an architecture rule;
report both outcomes. Do not silently turn one into the other.

## Controls

Record these in the manifest for every run:

- provider, base URL, exact model identifier/version, and response IDs;
- temperature `0`, top-p `1`, max output tokens, and seed if the provider
  supports it; otherwise record `seed: unsupported`;
- the `LLMAgent` system prompt and context limits (`full_context` disabled);
- one model call at a time, no tools, no network, no retries; any retry is a
  recorded failure attempt;
- Python version, `knowledge-surface` version, git commit, OS, and CPU;
- prompt order and task order, so a rerun is byte-identical apart from model
  output.

## Recorded artifacts

Write each run under `benchmarks/live_llm_runs/<UTC>-<model-slug>/`:

```text
manifest.json              # settings, environment, task hashes
responses/<task>-<arm>-<n>.txt   # raw model output, exact bytes
changes/<task>-<arm>-<n>.json    # parsed change set or parse error
tests/<task>-<arm>.log           # hidden-test output and exit code
result.json                # per-task outcomes and aggregate metrics
failures.md                # every failure with its category and evidence
```

Never delete a failed attempt. A `result.json` is written only after every task
in the frozen set has run through both arms. A partial run is recorded as
partial and is not reported as a pass rate.

## Failure categories

Classify each failure, in order:

1. model/network error;
2. invalid JSON or rejected path;
3. verifier rejected and no valid revision remained;
4. hidden tests failed;
5. timeout;
6. or the model produced a valid change but the run was interrupted.

Report the count for each category, not only an aggregate.

## Fail-closed command

The runner must exit non-zero and write no result when credentials or a model
are absent. `--dry-run` may validate the task layout and print the plan, but it
must not call a model or claim success.

```bash
LLM_API_KEY=... LLM_MODEL=... LLM_BASE_URL=... \
  .venv/bin/python benchmarks/live_llm_experiment.py \
  --tasks benchmarks/live_llm/tasks \
  --out benchmarks/live_llm_runs \
  --max-iterations 3

# layout/plan check only; no model call, no result file
.venv/bin/python benchmarks/live_llm_experiment.py \
  --tasks benchmarks/live_llm/tasks --dry-run
```

The runner is not part of the current evidence. Add it only with the frozen
task set; do not publish a pass rate until the run artifacts exist.
