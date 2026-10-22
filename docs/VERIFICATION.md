# Semantic Verification

The original checker flagged any change that *touched* an invariant's scope. That is useless in practice: it fires on every refactor and trains developers to ignore it. This engine instead decides whether a change actually **regresses** a rule.

## How it works

1. Parse the change set against a real base checkout. Patches that do not apply, do not supply a base for modified/deleted files, or contain malformed hunks are rejected with a diagnostic. The parser never invents source.
2. Build the before and after source trees (the after tree is the before tree with the change set overlaid).
3. Evaluate every rule against both trees.
4. A finding **blocks** only when the rule passed before and fails after — a new regression.
5. A rule that failed before and still fails after is reported as **pre-existing debt** and does not block.
6. A result that cannot be evaluated is **`UNKNOWN`**, is never treated as a pass, and is never classified as pre-existing.
7. A rule that fails but is suppressed by an allowlist is reported as **suppressed**.

This is why safe refactors and legacy debt produce zero false positives in the benchmark.

## Tri-state classification

| Before | After | Classification | Blocks by default |
|---|---|---|---|
| `PASS` | `FAIL` | introduced | yes |
| `FAIL` | `FAIL` | pre-existing | no |
| `UNKNOWN` | `FAIL` | unknown | yes |
| any | `UNKNOWN` | unknown | yes |
| `UNKNOWN` | `PASS` | improvement | no |

`unknown` is a first-class report section. `--unknown-policy` selects `block` (default), `warn` (report, but do not fail), or `ignore` (drop unknown findings; not recommended for a gate). Parse failures are reported in `parse_errors` and make affected rules `UNKNOWN` rather than silently passing.

## Rule types

| Rule | Checks |
|---|---|
| `forbidden_import` | a source path must not import a module (layer/security boundaries) |
| `forbidden_call` | a scope must not call a function (`eval`, `exec`, `float`, ...) |
| `require_call` | a function (optionally scoped by owner class) must call a guard before a sensitive call |
| `required_decorator` | a function must carry a named decorator |
| `type_annotation` | public functions are fully annotated |
| `no_mutable_default` | no mutable default arguments |
| `behavioral` | runs a Python assertion against the post-change tree in a subprocess |

`require_call` and `required_decorator` fail when the target function is absent. Set `"required": false` on a rule only when absence is genuinely acceptable. `require_call` also supports `owner` scoping, which matters in real code: `SigningAlgorithm.verify_signature` and `Signer.verify_signature` are different functions with the same name (`pallets/itsdangerous`). Calls in nested functions or lambdas do not satisfy the rule, and the required call must dominate the sensitive call (or a conditional in which every branch makes it).

## Behavioural rules

`behavioral` rules execute project-authored Python. They run in a temporary tree with:

- a minimal environment (`-E -s`; no inherited secrets or `PYTHONPATH`),
- a wall-clock timeout and a POSIX CPU/memory/file-size limit where available,
- a new process group killed with `SIGKILL` on timeout, so child processes do not survive,
- combined stdout/stderr bounded to 16 KiB.

This is **process isolation, not a security sandbox**. A snippet with access to the host interpreter can still do damage. Behavioral rules are refused unless the config sets `"trusted": true`; the API requires `allow_untrusted_behavioral=True` as an explicit opt-in, and that opt-in is only appropriate inside a real container or VM.

## Configuration

```json
{
  "rules": [
    {"type": "forbidden_import", "id": "layer-route-no-db",
     "source": "app/routes/.*\\.py$", "forbidden": "app\\.db"},
    {"type": "require_call", "id": "delete-authorize",
     "function": "^delete_account$", "callee": "authorize", "before_call": "delete"},
    {"type": "required_decorator", "id": "login-required",
     "function": "^secret_page$", "decorator": "login_required"},
    {"type": "behavioral", "id": "totals-nonnegative", "trusted": true,
     "snippet": "def check():\n    from app.pricing import total\n    assert total([]) == 0\n"}
  ],
  "allowlist": [["some-rule", "legacy/module.py"]]
}
```

## CLI contract

```bash
ks verify path/to/repo --patch change.patch --rules rules.json
```

| Exit | Meaning |
|---|---|
| `0` | approved (or unknown under `warn`/`ignore`) |
| `1` | policy rejection: at least one introduced failure |
| `2` | input error: bad patch, bad config, unreadable file |
| `3` | indeterminate: unknown results under a blocking policy |

`--json-out report.json` writes the full report, including `unknown`, `pre_existing`, `improvements`, `parse_errors`, and per-rule results.

## Honest limits

- Structural rules reason over syntax and a conservative call graph, not full data flow. A violation hidden behind dynamic dispatch may be reported `UNKNOWN` rather than `KNOWN`; ambiguous or locally shadowed call targets are skipped rather than guessed.
- Behavioral rules execute code. The controls above reduce accidental damage; they do not contain a determined attacker.
- Rules must be declared. The engine cannot invent an invariant that was never written anywhere; that is the whitepaper's tacit-knowledge problem.
