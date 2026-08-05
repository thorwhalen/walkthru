"""Guard the CI trigger shape that keeps a TS-only change from publishing Python (issue #23).

walkthru ships two packages from one repo: the Python package at the root (published to PyPI by
``.github/workflows/ci.yml`` via i2mint/wads' reusable ``uv-ci.yml``) and the TypeScript package in
``ts/`` (published to npm by ``.github/workflows/npm-ci-ts.yml``, which is already filtered to
``ts/**``).

The reusable workflow's publish job auto-bumps the version and uploads to PyPI on **every** push to
the default branch. With an unfiltered ``on: [push, pull_request]`` a TS-only commit therefore
burned a Python version number that contained no Python change — three times before this guard
existed, and a PyPI version number can be yanked but never reused.

Two invariants, and they pull in opposite directions, which is why both are asserted:

1. The ``push`` trigger **is** path-filtered so a TS-only push never reaches the publish job.
2. The ``pull_request`` trigger is **not** path-filtered, so the Python test matrix still runs on
   every PR — including TS-only ones. Gating the whole workflow instead of the publish would trade
   a redundant release for a silently-skipped test suite, which is the worse failure.

Deliberately dependency-free: walkthru's only runtime dependency is pydantic and CI installs no
test extras, so there is no YAML parser available. The reader below understands exactly the
indentation-based block mapping this one file uses.
"""

from __future__ import annotations

from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[1] / ".github" / "workflows" / "ci.yml"

#: Paths that belong to the TypeScript package only. A push touching nothing else must not
#: reach the Python publish job.
TS_ONLY_PATHS = ("ts/**",)


def _significant_lines(text: str) -> list[str]:
    """Right-stripped lines with blanks and whole-line comments dropped."""
    return [
        line.rstrip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _child_block(lines: list[str], key: str, indent: int) -> list[str] | None:
    """The lines nested under ``<indent spaces><key>:``, or ``None`` if that key is absent.

    A key present but with no nested lines (``pull_request:``) yields ``[]`` — distinguishable
    from absent, which is the distinction both tests below depend on.
    """
    prefix = " " * indent + key + ":"
    for i, line in enumerate(lines):
        if line == prefix or line.startswith(prefix + " "):
            body: list[str] = []
            for nxt in lines[i + 1 :]:
                if len(nxt) - len(nxt.lstrip(" ")) <= indent:
                    break
                body.append(nxt)
            return body
    return None


def _on_block() -> list[str]:
    lines = _significant_lines(WORKFLOW.read_text(encoding="utf-8"))
    block = _child_block(lines, "on", 0)
    assert block, (
        "ci.yml has no `on:` block mapping. The flow-style `on: [push, pull_request]` cannot "
        "carry the path filter that keeps a TS-only push from publishing Python (issue #23)."
    )
    return block


def test_push_trigger_excludes_ts_only_changes():
    """A push confined to ``ts/**`` must not trigger this workflow — hence not its publish job."""
    push = _child_block(_on_block(), "push", 2)
    assert push is not None, "ci.yml declares no `push:` trigger."

    ignored = _child_block(push, "paths-ignore", 4)
    assert ignored, (
        "ci.yml's `push:` trigger has no `paths-ignore:`. Without it a TS-only push to the "
        "default branch reaches the reusable workflow's publish job and burns a PyPI version "
        "number for a change containing no Python (issue #23)."
    )
    entries = {line.strip().lstrip("- ").strip("\"'") for line in ignored}
    missing = [p for p in TS_ONLY_PATHS if p not in entries]
    assert not missing, (
        f"ci.yml's `push: paths-ignore:` does not exclude {missing}. Every TypeScript-only path "
        f"must be listed, or a change to it still rolls the Python version. got={sorted(entries)}"
    )


def test_pull_request_trigger_is_not_path_filtered():
    """The Python test matrix must still run on every PR, including TS-only ones.

    The fix for issue #23 gates the *publish*, which is reachable only from a push to the default
    branch. Filtering ``pull_request`` too would silence the Python tests on TS-only PRs — trading
    a redundant release for missing test signal.
    """
    pull_request = _child_block(_on_block(), "pull_request", 2)
    assert pull_request is not None, "ci.yml declares no `pull_request:` trigger."

    filters = [
        line.strip()
        for line in pull_request
        if line.strip().startswith(("paths:", "paths-ignore:"))
    ]
    assert not filters, (
        "ci.yml's `pull_request:` trigger is path-filtered "
        f"({filters}). Issue #23 asks for a gate on the PUBLISH, not on the whole workflow: "
        "PRs must keep running the Python test matrix whatever they touch."
    )
