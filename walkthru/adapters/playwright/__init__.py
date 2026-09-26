"""Playwright adapters — ``ElementLocator``, ``Recorder`` and ``ReadinessWaiter`` (PLAN §3.4).

The three ports that resolve to Playwright on the Python side. All operate on an injected,
duck-typed Playwright object, so the core stays vendor-free and they are unit-testable without a
browser; install the optional extra (``pip install walkthru[playwright]``) only to drive a real
browser. The ``acture`` ``CommandPlayer`` and the driver.js ``CueRenderer`` are the other
web-first adapters and live on the TS side.

Two recorders: :class:`PlaywrightRecorder` (Playwright's own WebM screencast, any browser) and
:class:`CdpScreencastRecorder` (Chrome's DevTools screencast: crisp device-resolution frames with
timestamps, encoded as a constant-rate mp4 — what a narrated tour is cut from).
"""

from walkthru.adapters.playwright.cursor import (
    DEFAULT_CURSOR_SIZE,
    cursor_script,
    install_synthetic_cursor,
)
from walkthru.adapters.playwright.player import (
    PAGE_COMMANDS,
    PlaywrightCommandPlayer,
    UnknownCommandError,
)
from walkthru.adapters.playwright.locator import (
    ElementNotFoundError,
    PlaywrightElementLocator,
    build_locator,
)
from walkthru.adapters.playwright.readiness import (
    DEFAULT_READINESS_TIMEOUT_MS,
    PlaywrightReadinessWaiter,
    ReadinessTimeoutError,
)
from walkthru.adapters.playwright.screencast import (
    CdpScreencastRecorder,
    screencast_launch_args,
)
from walkthru.adapters.playwright.recorder import (
    DEFAULT_VIDEO_MIME,
    PlaywrightRecorder,
    RecorderError,
    RecorderStateError,
    new_recording_page,
)

__all__ = [
    "DEFAULT_CURSOR_SIZE",
    "cursor_script",
    "install_synthetic_cursor",
    "PAGE_COMMANDS",
    "PlaywrightCommandPlayer",
    "UnknownCommandError",
    "PlaywrightElementLocator",
    "ElementNotFoundError",
    "build_locator",
    "PlaywrightReadinessWaiter",
    "ReadinessTimeoutError",
    "DEFAULT_READINESS_TIMEOUT_MS",
    "PlaywrightRecorder",
    "RecorderError",
    "RecorderStateError",
    "new_recording_page",
    "DEFAULT_VIDEO_MIME",
    "CdpScreencastRecorder",
    "screencast_launch_args",
]
