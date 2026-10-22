# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| `0.3.x` | Yes |
| `0.2.x` and earlier | No |

## Reporting a vulnerability

Use GitHub's private vulnerability reporting on this repository: **Security → Report a vulnerability**. If that is unavailable, open a minimal issue that says a private report is needed; do not include exploit details or secrets in a public issue.

Please include the version, a reproduction, and the impact. You will get an acknowledgement as soon as the maintainer sees it. There is no bounty program and no formal SLA.

## Threat model

The verifier consumes three kinds of untrusted input:

1. **Patches and repository paths.** Paths from a diff or model response are normalized and checked for containment after symlink resolution. Absolute paths, `..` traversal, NUL bytes, and symlink escapes are rejected.
2. **Rule configuration and model output.** JSON is schema-validated. Unsafe or duplicate paths are rejected. Model prompts are bounded and common secret assignments are redacted before sending; this reduces accidental disclosure, not a hostile model provider.
3. **Behavioral-rule snippets.** A `behavioral` rule executes Python. It runs in a temporary tree with a minimal environment, a wall-clock timeout, a new process group killed with `SIGKILL`, POSIX resource limits where available, and output bounded to 16 KiB. **This is process isolation, not a security sandbox.** It does not stop a determined attacker with access to the host interpreter. Untrusted snippets are refused by default (`trusted: true` or `allow_untrusted_behavioral=True` is required), and that opt-in should only be used inside a container or VM.

Out of scope: denial of service against the host by deliberately trusted code, vulnerabilities in third-party dependencies (report those upstream), and the accuracy limits documented in the README and `docs/VERIFICATION.md`.

## Dependencies

Runtime dependencies are limited to `pydantic`, `networkx`, `click`, and `rich`. CI runs the test suite and lint on every push, plus `pip-audit --skip-editable` in the `dependency audit` job. The local 0.3.1 environment reported no known vulnerabilities. `pip-audit` is advisory-data dependent; a clean scan is not proof that dependencies are vulnerability-free.
