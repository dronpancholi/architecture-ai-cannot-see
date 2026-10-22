"""Smoke test for the CLI."""

import subprocess
import sys
from pathlib import Path


def test_cli_build_and_inspect(tmp_path):
    root = Path(__file__).resolve().parents[1] / "examples" / "demo_codebase"
    out = tmp_path / "ks.json"
    r = subprocess.run([sys.executable, "-m", "knowledge_surface.cli", "build", str(root), "-o", str(out)],
                       capture_output=True, text=True)
    # module may not be runnable; fall back to ks entrypoint
    if r.returncode != 0:
        r = subprocess.run(["ks", "build", str(root), "-o", str(out)], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert out.exists()
    r2 = subprocess.run(["ks", "inspect", str(out)], capture_output=True, text=True)
    assert r2.returncode == 0
