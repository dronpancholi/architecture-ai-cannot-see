"""Behavioural-rule execution.

This is *process isolation*, not a security sandbox. A trusted project-authored
snippet runs in a temporary tree with a minimal environment, a wall-clock
timeout, a process group that is killed on timeout, bounded file output, and
POSIX resource limits. Untrusted snippets are refused by default because none
of this stops a determined attacker with access to the host interpreter.

If a real OS/container sandbox is required, run the verifier inside one and
pass ``allow_untrusted_behavioral=True`` deliberately.
"""

from __future__ import annotations

import os
import signal
import subprocess
import sys
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path

from ..paths import safe_write
from .rules import Outcome

MAX_OUTPUT_BYTES = 16_384


@dataclass
class BehavioralResult:
    outcome: Outcome
    message: str
    evidence: str = ""


def _limits(timeout: float):
    def apply() -> None:  # pragma: no cover - executed in the child
        try:
            import resource

            cpu = max(1, int(timeout) + 1)
            resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
            resource.setrlimit(resource.RLIMIT_AS, (1 << 30, 1 << 30))
            resource.setrlimit(resource.RLIMIT_FSIZE, (10 << 20, 10 << 20))
            resource.setrlimit(resource.RLIMIT_NOFILE, (64, 64))
        except (ImportError, OSError, ValueError):
            pass

    return apply if os.name == "posix" else None


def _tail(path: Path, limit: int = MAX_OUTPUT_BYTES) -> str:
    try:
        data = path.read_bytes()
    except OSError:
        return ""
    if len(data) > limit:
        data = b"...[truncated]...\n" + data[-limit:]
    return data.decode("utf-8", errors="replace").strip()


def run_behavioral(
    snippet: str,
    tree: dict[str, str],
    *,
    trusted: bool,
    allow_untrusted: bool = False,
    timeout: float = 5.0,
) -> BehavioralResult:
    if not trusted and not allow_untrusted:
        return BehavioralResult(
            Outcome.UNKNOWN,
            "refused to execute untrusted behavioural rule",
            "Mark the rule trusted=true or pass allow_untrusted_behavioral=True "
            "inside an isolated runner.",
        )
    if timeout <= 0 or timeout > 300:
        return BehavioralResult(Outcome.UNKNOWN, f"invalid behavioural timeout: {timeout}")

    with tempfile.TemporaryDirectory(prefix="ks-behavior-") as td:
        root = Path(td)
        try:
            for rel, content in tree.items():
                safe_write(root, rel, content)
            harness = root / "_ks_behavior_check.py"
            safe_write(
                root,
                harness.name,
                textwrap.dedent(snippet)
                + "\n\nif __name__ == '__main__':\n    check()\n",
            )
        except (OSError, ValueError) as exc:
            return BehavioralResult(Outcome.UNKNOWN, f"cannot stage behavioural check: {exc}")

        out_path = root / "_ks_stdout.txt"
        err_path = root / "_ks_stderr.txt"
        env = {
            "PATH": os.environ.get("PATH", "/usr/bin:/bin"),
            "HOME": str(root),
            "TMPDIR": str(root),
            "LANG": "C.UTF-8",
            "PYTHONHASHSEED": "0",
            "PYTHONDONTWRITEBYTECODE": "1",
        }
        try:
            with out_path.open("wb") as out, err_path.open("wb") as err:
                proc = subprocess.Popen(
                    [sys.executable, "-E", "-s", str(harness)],
                    cwd=root,
                    stdin=subprocess.DEVNULL,
                    stdout=out,
                    stderr=err,
                    env=env,
                    start_new_session=True,
                    preexec_fn=_limits(timeout),
                )
                try:
                    code = proc.wait(timeout=timeout)
                except subprocess.TimeoutExpired:
                    _kill(proc)
                    return BehavioralResult(
                        Outcome.UNKNOWN,
                        f"behavioural check timed out after {timeout}s",
                        _tail(err_path) or "timeout",
                    )
        except OSError as exc:
            return BehavioralResult(Outcome.UNKNOWN, f"cannot start behavioural check: {exc}")

        if code == 0:
            return BehavioralResult(Outcome.PASS, "behavioural check passed")

        detail = (_tail(out_path) + "\n" + _tail(err_path)).strip()
        lines = [line for line in detail.splitlines() if line.strip()]
        message = (lines[-1] if lines else f"behavioural check failed with exit code {code}")[:500]
        evidence = "\n".join(lines[-20:])
        if len(evidence) > MAX_OUTPUT_BYTES:
            evidence = "...[truncated]...\n" + evidence[-MAX_OUTPUT_BYTES:]
        return BehavioralResult(
            Outcome.FAIL,
            f"behavioural violation: {message}",
            evidence,
        )


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        else:  # pragma: no cover - non-POSIX fallback
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        try:
            proc.kill()
        except OSError:
            pass
    try:
        proc.wait(timeout=2)
    except subprocess.TimeoutExpired:
        pass
