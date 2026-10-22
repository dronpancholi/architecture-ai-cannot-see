"""External benchmark: run the verifier against real public repositories.

Targets two small, real, security-sensitive libraries:
  - pallets/itsdangerous
  - psf/requests

This demonstrates that the engine is not overfit to the toy fixtures.

Usage:
    python benchmarks/external.py [--path /path/to/repo] [--keep] [--out FILE]
"""

from __future__ import annotations

import argparse
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


def clone(target: Target, dest: Path) -> None:
    subprocess.run(["git", "clone", "--depth", "1", "-q", target.repo, str(dest)], check=True)


def run_target(target: Target, root: Path) -> list[Result]:
    results: list[Result] = []
    for s in target.scenarios:
        path = root / s.path
        before = path.read_text()
        assert s.old in before, f"anchor not found for {s.name}"
        after = before.replace(s.old, s.new, 1)
        changes = ChangeSet(files=[FileChange(path=s.path, before=before, after=after)])
        report = SemanticVerifier(s.rules).verify(root, changes)
        results.append(Result(
            scenario=s.name, category=s.category,
            expected_blocked=s.expected_blocked,
            predicted_blocked=not report.approved,
            summary=report.summary(),
            findings=[f.to_dict() for f in report.findings],
        ))
    return results


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", type=Path, default=None, help="Use an existing checkout.")
    parser.add_argument("--keep", action="store_true")
    parser.add_argument("--out", type=Path, default=Path(__file__).resolve().parent / "EXTERNAL.md")
    args = parser.parse_args()

    sections: list[str] = []
    all_results: list[Result] = []
    for target in targets():
        tmp = None
        if args.path:
            root = args.path
        else:
            tmp = tempfile.mkdtemp(prefix="ks-external-")
            root = Path(tmp) / "repo"
            clone(target, root)
        try:
            results = run_target(target, root)
            all_results.extend(results)
            agg = aggregate(results)
            md = to_markdown(results, agg)
            sections.append(md.replace(
                "# Benchmark Results",
                f"# {target.name} @ {target.pin[:7]}",
            ))
        finally:
            if tmp and not args.keep:
                shutil.rmtree(tmp, ignore_errors=True)

    header = "# External Benchmark — Real Public Repositories\n\n"
    combined = to_markdown(all_results, aggregate(all_results)).replace("# Benchmark Results", "").lstrip()
    footer = "\n## Combined\n\n" + combined
    out = header + "\n".join(sections) + footer
    args.out.write_text(out)
    print(out)


if __name__ == "__main__":
    main()
