"""Regression checks for the local performance baseline."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "benchmarks"))

from perf import _p95  # noqa: E402


def test_p95_uses_nearest_rank():
    assert _p95([1]) == 1
    assert _p95([1, 2, 3, 4, 5]) == 5
    assert _p95(list(range(1, 21))) == 19
