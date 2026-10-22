# Semantic Verification

The original checker flagged any change that *touched* an invariant's scope. That is useless in practice: it fires on every refactor and trains developers to ignore it. This engine instead decides whether a change actually **regresses** a rule.

## How it works

1. Parse the change set against a real base checkout. Patches that do not apply, do not supply a base for modified/deleted files, or contain malformed hunks are rejected with a diagnostic. The parser never invents source.
2. Build the before and after source trees (the after tree is the before tree with the change set overlaid).
3. Evaluate every rule against both trees. Each built-in rule records **every** violation with a stable semantic key, not only the first.
4. Match findings individually. Identity is `(canonical_path, semantic_key)`; line numbers are not identity. A file rename maps the after path to the old path. Repeated identical targets in one file get deterministic `#1`, `#2`, ... suffixes, so a second forbidden call/import is a new finding; counters are per file.
5. Only an **introduced** finding blocks. Old debt with the same identity is reported as **pre-existing**; an old finding that disappears is an **improvement**.
6. A result that cannot be evaluated is **`UNKNOWN`**, is never treated as a pass, and is never classified as pre-existing.
7. A rule that fails but is suppressed by an allowlist is reported as **suppressed**.

This is why safe refactors and legacy debt produce zero false positives in the benchmark, while a new violation beside existing debt is still blocked.

## Per-finding classification

| Before | After | Classification | Blocks by default |
|---|---|---|---|
| `PASS` | `FAIL` | every after finding is introduced | yes |
| `FAIL` | `PASS` | each before finding is an improvement | no |
| `FAIL` | `FAIL` | matching `(path, key)` is pre-existing; unmatched after findings are introduced | only the new ones |
| `UNKNOWN` | `FAIL` | unknown | yes |
| any | `UNKNOWN` | unknown | yes |

Examples that are explicitly tested:

- an existing forbidden import plus a new one in the same file;
- an existing violation in one file plus a new violation in another;
- two failing functions under one `require_call` rule;
- repaired old debt plus a new violation;
- unchanged debt while an unrelated file changes safely;
- a file rename that preserves debt, and a function rename that cannot be matched;
- duplicate function names, module-level calls, nested scopes, and multiple findings per file.

A function rename produces a new key and is treated as **introduced** (fail-closed). The engine does not guess that the new name is the old function.

`unknown` is a first-class report section. `--unknown-policy` selects `block` (default), `warn` (report, but do not fail), or `ignore` (drop rule-level unknown findings from the approval decision; `rule_results` and `parse_errors` remain visible).

## Parse and completeness policy

Parse errors are diagnostics, not silent passes:

- A **new** parse error in a changed file is an introduced `parse-error` finding. It blocks regardless of `unknown_policy`, including `warn` and `ignore`.
- A **pre-existing** parse error outside a rule's scope is a pre-existing diagnostic only. A scoped rule can still produce complete evidence for an unrelated change.
- A pre-existing parse error **inside** a rule's scope makes that rule `UNKNOWN` (for example, `forbidden_import` scoped to a file that does not parse).
- A **global-scope** rule reads the whole tree, so any pre-existing parse error can make it `UNKNOWN` and block under the default policy. This is deliberate fail-closed behaviour, not a claim that pre-existing debt can never block.
- `complete` is false when the change itself introduces an unparseable file or contains unsupported content. A pre-existing error elsewhere does not make the change incomplete.

Behavioural rules are one check per rule. Their stable key is `behavior::<rule_id>`; a custom `RuleResult` without per-violation entries falls back to a message-based key and is documented as fail-closed.

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

`--json-out report.json` writes the full report, including `findings`, `preexisting`, `improvements`, `unknown`, `parse_errors`, `rule_results`, and stable per-finding `key` values. `rule_results` also records `violations_before` and `violations_after`.

## Honest limits

- Structural rules reason over syntax and a conservative call graph, not full data flow. A violation hidden behind dynamic dispatch may be reported `UNKNOWN` rather than `KNOWN`; ambiguous or locally shadowed call targets are skipped rather than guessed.
- Behavioral rules execute code. The controls above reduce accidental damage; they do not contain a determined attacker.
- Rules must be declared. The engine cannot invent an invariant that was never written anywhere; that is the whitepaper's tacit-knowledge problem.
