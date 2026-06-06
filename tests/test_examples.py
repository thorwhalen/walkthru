"""The ``examples/`` scripts must keep running — they are executable documentation.

Each example is run as a subprocess exactly as a reader would (``python examples/<name>.py``),
asserting a clean exit and a sentinel line of output. This guards against the examples drifting
out of sync with the public API (a renamed export or changed signature breaks them here, in CI,
rather than silently in the README). The examples are deliberately pure-core, so this needs no
optional dependency.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

EXAMPLES_DIR = Path(__file__).resolve().parent.parent / "examples"


@pytest.mark.parametrize(
    ("script", "sentinel"),
    [
        ("generative_demo.py", "Outcome: ok=True, steps_run=2"),
        ("capture_demo.py", "Round-trip verified"),
    ],
)
def test_example_runs(script: str, sentinel: str) -> None:
    path = EXAMPLES_DIR / script
    result = subprocess.run(
        [sys.executable, str(path)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, (
        f"{script} exited {result.returncode}:\n{result.stderr}"
    )
    assert sentinel in result.stdout, (
        f"{script} missing sentinel {sentinel!r}:\n{result.stdout}"
    )
