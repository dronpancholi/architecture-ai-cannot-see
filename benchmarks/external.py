"""External benchmark: run the verifier against real public repositories.

Targets two small, real, security-sensitive libraries:
  - pallets/itsdangerous
  - psf/requests

The benchmark fetches the exact commit declared by each target, checks it out
detached, and verifies ``git rev-parse HEAD`` before running any scenario. It
fails loudly on a wrong revision, a missing anchor, or an indeterminate
verification result.

Usage:
    python benchmarks/external.py
    python benchmarks/external.py --target itsdangerous
    python benchmarks/external.py --target itsdangerous --path /path/to/checkout
    python benchmarks/external.py --keep
"""

from __future__ import annotations

import argparse
import importlib.metadata
import json
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from runner import Result, aggregate, to_markdown

from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier
from knowledge_surface.verification.rules import (
    ForbiddenCallRule,
    ForbiddenImportRule,
    RequireCallRule,
    Rule,
)


class BenchmarkError(RuntimeError):
    """The benchmark cannot make a reproducible, gradeable claim."""


@dataclass
class ExtScenario:
    name: str
    category: str
    expected_blocked: bool
    rules: list[Rule]
    path: str
    old: str
    new: str


@dataclass
class Target:
    name: str
    repo: str
    pin: str
    scenarios: list[ExtScenario] = field(default_factory=list)


def itsdangerous() -> Target:
    security = [
        RequireCallRule(
            "constant-time-compare", r"^verify_signature$", "compare_digest",
            owner=r"^SigningAlgorithm$",
            description="signature verification must use a constant-time comparison",
        ),
    ]
    serializer = [
        ForbiddenImportRule(
            "no-pickle", r"^src/itsdangerous/serializer\.py$", r"^pickle$",
            "serializer must not import pickle (unsafe deserialization)",
        ),
    ]
    signer_no_pickle = [
        ForbiddenImportRule("signer-no-pickle", r"^src/itsdangerous/signer\.py$", r"^pickle$",
                            "signer must not import pickle"),
    ]
    return Target("pallets/itsdangerous", "https://github.com/pallets/itsdangerous.git",
                  "672971d66a2ef9f85151e53283113f33d642dabd", [
        ExtScenario("itsdangerous-constant-time", "introduced-violation", True,
                    security, "src/itsdangerous/signer.py",
                    "return hmac.compare_digest(sig, self.get_signature(key, value))",
                    "return sig == self.get_signature(key, value)"),
        ExtScenario("itsdangerous-signer-pickle", "introduced-violation", True,
                    signer_no_pickle, "src/itsdangerous/signer.py",
                    "import hashlib\nimport hmac", "import hashlib\nimport hmac\nimport pickle"),
        ExtScenario("itsdangerous-safe-docstring", "safe-refactor", False,
                    security, "src/itsdangerous/signer.py",
                    '    def get_signature(self, key: bytes, value: bytes) -> bytes:\n        """Returns the signature for the given key and value."""',
                    '    def get_signature(self, key: bytes, value: bytes) -> bytes:\n        """Return the signature for the given key and value.\n\n        This must remain deterministic for a given key and value.\n        """'),
        ExtScenario("itsdangerous-pickle", "introduced-violation", True,
                    serializer, "src/itsdangerous/serializer.py",
                    "import typing as t", "import pickle\nimport typing as t"),
        ExtScenario("itsdangerous-safe-rename", "safe-refactor", False,
                    [], "src/itsdangerous/signer.py",
                    "        mac = hmac.new(key, msg=value, digestmod=self.digest_method)\n        return mac.digest()",
                    "        digest = hmac.new(key, msg=value, digestmod=self.digest_method)\n        return digest.digest()"),
    ])


def requests_target() -> Target:
    rules = [
        ForbiddenImportRule(
            "requests-no-pickle", r"^src/requests/sessions\.py$", r"^pickle$",
            "sessions must not import pickle",
        ),
        ForbiddenImportRule(
            "requests-no-subprocess", r"^src/requests/sessions\.py$", r"^subprocess$",
            "sessions must not shell out",
        ),
    ]
    eval_rules = [ForbiddenCallRule("auth-no-eval", r"^src/requests/auth\.py$", "eval",
                                    "auth must not eval")]
    return Target("psf/requests", "https://github.com/psf/requests.git",
                  "611c6162cbc4ac2020a2f91c7cfa4f3abf9bbb60", [
        ExtScenario("requests-eval", "introduced-violation", True,
                    eval_rules, "src/requests/auth.py",
                    "class AuthBase:", "class AuthBase:\n    def unsafe(self, code: str):\n        return eval(code)"),
        ExtScenario("requests-pickle", "introduced-violation", True,
                    rules, "src/requests/sessions.py",
                    "import os\nimport sys", "import os\nimport pickle\nimport sys"),
        ExtScenario("requests-subprocess", "introduced-violation", True,
                    rules, "src/requests/sessions.py",
                    "import os\nimport sys", "import subprocess\nimport os\nimport sys"),
        ExtScenario("requests-safe-docstring", "safe-refactor", False,
                    rules, "src/requests/api.py",
                    "This module implements the Requests API.",
                    "This module implements the Requests API.\n\nAll helpers return a Response."),
        ExtScenario("requests-safe-rename", "safe-refactor", False,
                    rules, "src/requests/sessions.py",
                    "from ._internal_utils import to_native_string",
                    "from ._internal_utils import to_native_string as _to_native_string"),
    ])


def targets() -> list[Target]:
    return [itsdangerous(), requests_target()]


def _git(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], check=check, capture_output=True, text=True, timeout=180,
    )


def checkout(target: Target, dest: Path) -> str:
    """Fetch and check out the declared pin; return the verified HEAD."""
    dest.mkdir(parents=True, exist_ok=True)
    try:
        _git(["init", "-q", str(dest)])
        _git(["-C", str(dest), "remote", "add", "origin", target.repo])
        fetched = _git(
            ["-C", str(dest), "fetch", "--depth", "1", "-q", "origin", target.pin],
            check=False,
        )
        if fetched.returncode != 0:
            _git(["-C", str(dest), "fetch", "-q", "origin"])
        _git(["-C", str(dest), "checkout", "-q", "--detach", target.pin])
        head = _git(["-C", str(dest), "rev-parse", "HEAD"]).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        detail = getattr(exc, "stderr", "") or str(exc)
        raise BenchmarkError(
            f"{target.name}: cannot check out {target.pin} from {target.repo}: {detail}"
        ) from exc
    if head != target.pin:
        raise BenchmarkError(
            f"{target.name}: checkout is at {head}, expected pinned {target.pin}"
        )
    return head


def _verify_checkout(target: Target, root: Path) -> None:
    if not (root / ".git").exists():
        raise BenchmarkError(f"{target.name}: --path is not a git checkout: {root}")
    try:
        head = _git(["-C", str(root), "rev-parse", "HEAD"]).stdout.strip()
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise BenchmarkError(f"{target.name}: cannot read HEAD in {root}") from exc
    if head != target.pin:
        raise BenchmarkError(
            f"{target.name}: --path HEAD is {head}, expected pinned {target.pin}"
        )


def run_target(target: Target, root: Path) -> list[Result]:
    results: list[Result] = []
    for s in target.scenarios:
        path = root / s.path
        if not path.is_file():
            raise BenchmarkError(
                f"{s.name}: source file not found: {s.path} "
                f"({target.name} @ {target.pin})"
            )
        before = path.read_text(encoding="utf-8")
        if s.old not in before:
            raise BenchmarkError(
                f"{s.name}: anchor not found in {s.path} "
                f"({target.name} @ {target.pin})"
            )
        after = before.replace(s.old, s.new, 1)
        if after == before:
            raise BenchmarkError(f"{s.name}: scenario made no change")
        changes = ChangeSet(files=[FileChange(path=s.path, before=before, after=after)])
        report = SemanticVerifier(s.rules).verify(root, changes)
        if report.unknown or not report.complete:
            raise BenchmarkError(
                f"{s.name}: indeterminate verification for {target.name} @ {target.pin}: "
                f"{report.summary()}"
            )
        results.append(Result(
            scenario=s.name, category=s.category,
            expected_blocked=s.expected_blocked,
            predicted_blocked=not report.approved,
            summary=report.summary(),
            findings=[f.to_dict() for f in report.findings],
            unknown=len(report.unknown),
            complete=report.complete,
        ))
    return results


def _select(all_targets: list[Target], selector: str | None) -> list[Target]:
    if selector is None:
        return all_targets
    matches = [t for t in all_targets if selector in t.name]
    if len(matches) != 1:
        names = ", ".join(t.name for t in all_targets)
        raise BenchmarkError(
            f"--target {selector!r} matched {len(matches)} targets; choose one of: {names}"
        )
    return matches


def _tool_version() -> str:
    try:
        return importlib.metadata.version("knowledge-surface")
    except importlib.metadata.PackageNotFoundError:
        return "unknown (source checkout)"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None,
                        help="Use an existing checkout (requires --target).")
    parser.add_argument("--target", default=None,
                        help="Run one target by name substring.")
    parser.add_argument("--keep", action="store_true", help="Keep temporary checkouts.")
    parser.add_argument("--out", type=Path,
                        default=Path(__file__).resolve().parent / "EXTERNAL.md")
    parser.add_argument("--json-out", type=Path,
                        default=Path(__file__).resolve().parent / "external.json")
    args = parser.parse_args()

    if args.path and not args.target:
        parser.error("--path requires --target so a checkout is not run against another project")

    selected = _select(targets(), args.target)
    sections: list[str] = []
    all_results: list[Result] = []
    metadata: list[dict] = []

    for target in selected:
        tmp: str | None = None
        if args.path:
            root = args.path.resolve()
            _verify_checkout(target, root)
        else:
            tmp = tempfile.mkdtemp(prefix="ks-external-")
            root = Path(tmp) / "repo"
            checkout(target, root)
        try:
            results = run_target(target, root)
            all_results.extend(results)
            agg = aggregate(results)
            metadata.append({
                "target": target.name,
                "repo": target.repo,
                "commit": target.pin,
                "scenarios": len(results),
                "aggregate": agg,
            })
            section = to_markdown(results, agg)
            section = section.replace(
                "# Benchmark Results",
                f"# {target.name} @ `{target.pin[:12]}`",
            )
            section = section.replace(
                "## Aggregate",
                f"- Repository: `{target.repo}`\n"
                f"- Commit: `{target.pin}`\n\n## Aggregate",
            )
            sections.append(section)
        finally:
            if tmp and not args.keep:
                shutil.rmtree(tmp, ignore_errors=True)

    total = aggregate(all_results)
    header = (
        "# External Benchmark — Real Public Repositories\n\n"
        f"- Tool: `knowledge-surface {_tool_version()}`\n"
        f"- Targets: {len(selected)}\n"
        f"- Scenarios: {len(all_results)}\n"
        "- Every checkout is pinned and HEAD-verified before scenarios run.\n"
        "- Unknown or incomplete results fail the benchmark instead of counting as a block.\n\n"
    )
    footer = "\n## Combined\n\n" + to_markdown(all_results, total).replace("# Benchmark Results", "").lstrip()
    out = header + "\n".join(sections) + footer
    args.out.write_text(out, encoding="utf-8")
    args.json_out.write_text(json.dumps({
        "tool_version": _tool_version(),
        "targets": metadata,
        "combined": total,
        "results": [r.__dict__ for r in all_results],
    }, indent=2, sort_keys=True), encoding="utf-8")
    print(out)


if __name__ == "__main__":
    main()
