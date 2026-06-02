"""Playwright adapters — the web-first ``ElementLocator`` and ``Recorder`` (PLAN §3.4).

The two ports that resolve to Playwright on the Python side. Both operate on an injected,
duck-typed Playwright object, so the core stays vendor-free and they are unit-testable without a
browser; install the optional extra (``pip install walkthru[playwright]``) only to drive a real
browser. The ``acture`` ``CommandPlayer`` and the driver.js ``CueRenderer`` are the other
web-first adapters and live on the TS side.
"""

from walkthru.adapters.playwright.locator import (
    ElementNotFoundError,
    PlaywrightElementLocator,
)
from walkthru.adapters.playwright.recorder import (
    DEFAULT_VIDEO_MIME,
    PlaywrightRecorder,
    RecorderError,
    RecorderStateError,
    new_recording_page,
)

__all__ = [
    "PlaywrightElementLocator",
    "ElementNotFoundError",
    "PlaywrightRecorder",
    "RecorderError",
    "RecorderStateError",
    "new_recording_page",
    "DEFAULT_VIDEO_MIME",
]
