"""The synthetic cursor overlay: the script it generates, and how it installs.

The quoting test below is not pedantry. An init script that fails to parse throws in a
context nobody is watching -- no exception reaches Python, the page renders normally, and
the only symptom is a finished video with no cursor in it. That is exactly how the first
version of this shipped, so the shape of the bug is pinned here.
"""

import re
import shutil
import subprocess

import pytest

from walkthru.adapters.playwright import (
    DEFAULT_CURSOR_SIZE,
    cursor_script,
    install_synthetic_cursor,
)


class FakePage:
    def __init__(self):
        self.scripts = []

    async def add_init_script(self, script):
        self.scripts.append(script)


def test_the_data_uri_carries_no_quote_characters():
    """A raw `utf8,<svg xmlns='http://...'>` URI ends the JS string at its apostrophe."""
    script = cursor_script()
    uri = re.search(r"url\(\"(data:image/svg\+xml[^\"]+)\"\)", script)
    assert uri, "the cursor image should be an inline data URI"
    assert "'" not in uri.group(1)
    assert uri.group(1).startswith("data:image/svg+xml;base64,")


@pytest.mark.parametrize("ring", [True, False])
@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_generated_script_parses(tmp_path, ring):
    path = tmp_path / "cursor.js"
    path.write_text(cursor_script(ring=ring), encoding="utf-8")
    result = subprocess.run(["node", "--check", str(path)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_the_overlay_cannot_intercept_what_it_demonstrates():
    script = cursor_script()
    assert "pointer-events: none" in script
    assert "z-index:2147483647" in script


def test_size_and_smoothing_reach_the_script():
    script = cursor_script(size=40, smoothing_ms=250)
    assert "width:40px" in script and "250ms" in script


def test_the_ring_is_optional():
    assert "mousedown" in cursor_script(ring=True)
    assert "mousedown" not in cursor_script(ring=False)


def test_the_script_is_idempotent():
    """Init scripts re-run on every navigation; the overlay must not stack up."""
    assert "__walkthruCursor" in cursor_script()


@pytest.mark.asyncio
async def test_install_adds_exactly_one_init_script():
    page = FakePage()
    await install_synthetic_cursor(page)
    assert len(page.scripts) == 1
    assert f"width:{DEFAULT_CURSOR_SIZE}px" in page.scripts[0]
