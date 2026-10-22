"""Local performance baseline for extraction, verification, and sandbox runs.

This is a regression guard, not a competitive benchmark. It measures the same
work on the same host and writes ``perf.json`` next to this file.

Usage:
    python benchmarks/perf.py [--iterations 20]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

from knowledge_surface.extractors.python_ast import PythonASTExtractor
from knowledge_surface.pipeline import build_surface
from knowledge_surface.verification.change import ChangeSet, FileChange
from knowledge_surface.verification.engine import SemanticVerifier
from knowledge_surface.verification.rules import ForbiddenImportRule
from knowledge_surface.verification.sandbox import run_behavioral

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "benchmarks" / "fixtures" / "layered_webapp"


def _p95(samples: list[float]) -> float:
    """Nearest-rank 95th percentile; for five samples this is the maximum."""
    ordered = sorted(samples)
    return ordered[min(len(ordered) - 1, math.ceil(0.95 * len(ordered)) - 1)]


def _time(fn, iterations: int) -> dict:
    samples: list[float] = []
    for _ in range(iterations):
        start = time.perf_counter()
        fn()
        samples.append((time.perf_counter() - start) * 1000)
    return {
        "iterations": iterations,
        "median_ms": round(statistics.median(samples), 2),
        "p95_ms": round(_p95(samples), 2),
        "min_ms": round(min(samples), 2),
        "max_ms": round(max(samples), 2),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--iterations", type=int, default=20)
    args = parser.parse_args()
    if args.iterations < 1:
        parser.error("--iterations must be at least 1")

    source_root = ROOT / "src" / "knowledge_surface"
    tracemalloc.start()
    build_start = time.perf_counter()
    surface = build_surface(source_root, name="perf")
    cold_build_ms = (time.perf_counter() - build_start) * 1000
    _, peak_bytes = tracemalloc.get_traced_memory()
    tracemalloc.stop()

    fixture_file = "app/routes/orders.py"
    before = (FIXTURE / fixture_file).read_text(encoding="utf-8")
    change = ChangeSet(files=[FileChange(
        path=fixture_file, before=before, after=before + "\n# perf probe\n",
    )])
    verifier = SemanticVerifier([
        ForbiddenImportRule("perf-rule", r"app/routes/.*\.py$", r"app\.db"),
    ])

    payload = {
        "command": f"python benchmarks/perf.py --iterations {args.iterations}",
        "output": "benchmarks/perf.json",
        "environment": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python": sys.version.split()[0],
            "implementation": platform.python_implementation(),
        },
        "host_python": sys.version.split()[0],
        "extractor_only": _time(
            lambda: PythonASTExtractor(source_root).build(), args.iterations
        ),
        "full_build": _time(
            lambda: build_surface(source_root, name="perf"), args.iterations
        ),
        "verify_safe_change": _time(
            lambda: verifier.verify(FIXTURE, change), args.iterations
        ),
        "sandbox": _time(
            lambda: run_behavioral(
                "def check():\n    assert 2 + 2 == 4\n",
                {"m.py": "x = 1\n"}, trusted=True, timeout=5.0,
            ),
            args.iterations,
        ),
        "cold_build_first_run": {
            "duration_ms": round(cold_build_ms, 2),
            "peak_tracemalloc_mb": round(peak_bytes / (1024 * 1024), 2),
            "files": surface.diagnostics.get("files_discovered"),
            "entities": len(surface.entities()),
            "relationships": len(surface.relationships()),
        },
        "fixture": str(FIXTURE.relative_to(ROOT)),
    }
    out = Path(__file__).resolve().parent / "perf.json"
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("# Local Performance Baseline\n")
    print(f"- Python: {payload['host_python']}")
    print(f"- Fixture: `{payload['fixture']}`")
    print(f"- Iterations per measurement: {args.iterations}\n")
    print("| Operation | Median | p95 | Min | Max |")
    print("|---|---|---|---|---|")
    for name in ("extractor_only", "full_build", "verify_safe_change", "sandbox"):
        row = payload[name]
        print(
            f"| {name} | {row['median_ms']:.2f} ms | {row['p95_ms']:.2f} ms "
            f"| {row['min_ms']:.2f} ms | {row['max_ms']:.2f} ms |"
        )
    cold = payload["cold_build_first_run"]
    print(
        f"\nCold full build: {cold['duration_ms']:.2f} ms, "
        f"{cold['peak_tracemalloc_mb']:.2f} MB peak, "
        f"{cold['files']} files, {cold['entities']} entities, "
        f"{cold['relationships']} relationships."
    )


if __name__ == "__main__":
    main()
