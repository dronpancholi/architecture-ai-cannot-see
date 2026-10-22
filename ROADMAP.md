# Roadmap

This is an honest list of what is missing, ordered by evidence value rather than novelty.

## Next

- **Live-model evaluation.** The loop is proven with a deterministic `ScriptedAgent`. Run a real model against the same 17 scenarios and record safe-change rate, iterations, token cost, and failure modes. Until then, no live-model claim is made.
- **Dependency-audit gate.** Add `pip-audit` (or equivalent) to CI and document the policy for runtime dependencies.
- **More external repositories.** The external benchmark pins two repositories and ten scenarios. Add projects with different shapes (Django, async services, data pipelines) and keep every target pinned by full SHA.
- **Data-flow-aware rules.** The current structural rules reason over syntax and a conservative call graph. A rule that needs argument provenance should be able to say `UNKNOWN` with a reason instead of a heuristic guess.

## Later

- **OS/container isolation for behavioural rules.** The current subprocess controls are documented as process isolation. A real sandbox (container, seccomp, or VM) would let untrusted snippets run safely.
- **Additional languages.** Python is the only extractor. TypeScript and Go are the obvious next targets; each needs its own conservative call-graph and import-resolution tests.
- **Incremental extraction.** Full builds are measured in hundreds of milliseconds on the project's own source, which is fine for a gate but wasteful for a watch loop.
- **Editor/agent integrations.** Expose the verifier as a stable JSON protocol for agent harnesses and editors. The CLI report is the current interface.
- **Calibrated confidence.** `KNOWN` / `INFERRED` / `UNKNOWN` is deliberately coarse. Any finer score needs calibration data that does not exist yet.

## Not planned

- Claiming a literal "10/10" or universal superiority. The benchmark is controlled and small; the external set is two repositories.
- Storing or transmitting credentials. The project needs none to build or verify.
- Silently passing when a check cannot run. `UNKNOWN` is a feature, not a failure to hide.
