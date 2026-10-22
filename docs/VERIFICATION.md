# Semantic Verification

The original checker flagged any change that *touched* an invariant's scope. That is useless in practice: it fires on every refactor and trains developers to ignore it. This engine instead decides whether a change actually **regresses** a rule.

## How it works

1. Build the before and after source trees (the after tree is the before tree with the change set overlaid).
2. Evaluate every rule against both trees.
3. A finding **blocks** only when the rule passed before and fails after — a new regression.
4. A rule that failed before and still fails after is reported as **pre-existing debt** and does not block.
5. A rule that fails but is suppressed by an allowlist is reported as **suppressed**.

This is why safe refactors and legacy debt produce zero false positives in the benchmark.

## Rule types

| Rule | Checks |
|---|---|
| `forbidden_import` | a source path must not import a module (layer/security boundaries) |
| `forbidden_call` | a scope must not call a function (`eval`, `exec`, `float`, ...) |
| `require_call` | a function (optionally scoped by owner class) must call a guard before a sensitive call |
| `type_annotation` | public functions are fully annotated |
| `no_mutable_default` | no mutable default arguments |
| `behavioral` | runs a Python assertion against the post-change tree in a subprocess |

`require_call` supports `owner` scoping, which matters in real code: `SigningAlgorithm.verify_signature` and `Signer.verify_signature` are different functions with the same name (`pallets/itsdangerous`).

## Honest limits

- Structural rules reason over syntax and the call graph, not full data flow. A violation hidden behind a dynamic dispatch may be reported `UNKNOWN` rather than `KNOWN`.
- `behavioral` rules execute code. They are sandboxed by a temp directory and a timeout, but they are not a security boundary. Run them on trusted code.
- Rules must be declared. The engine cannot invent an invariant that was never written anywhere; that is the whitepaper's tacit-knowledge problem.

## Configuration

```json
{
  "rules": [
    {"type": "forbidden_import", "id": "layer-route-no-db",
     "source": "app/routes/.*\\.py$", "forbidden": "app\\.db"},
    {"type": "require_call", "id": "delete-authorize",
     "function": "^delete_account$", "callee": "authorize", "before_call": "delete"}
  ],
  "allowlist": [["some-rule", "legacy/module.py"]]
}
```

```bash
ks verify path/to/repo --patch change.patch --rules rules.json
```
