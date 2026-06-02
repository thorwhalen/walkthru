"""Playwright ``Recorder`` — capture the page to a video asset via Playwright's screencast.

walkthru's first real :class:`~walkthru.ports.Recorder` (PLAN §3.4). Playwright records video at
the **browser-context** level: a context created with ``record_video_dir`` films every page for
that page's lifetime, and the file is finalized when the page (or context) closes. This adapter
maps that model onto the port's ``start()`` / ``stop()`` shape:

- construct it with a page whose context was created with ``record_video_dir`` set (see
  :func:`new_recording_page`);
- :meth:`start` marks the recording window open — the page is already filming, so ``start`` is the
  explicit "from here" lifecycle marker (and a guard against double use);
- :meth:`stop` closes the page to finalize the file, then returns the written video as an
  :class:`~walkthru.core.schema.AssetRef` — at a stable ``save_as`` path when one was given, else
  the path Playwright chose.

Like the locator, this imports nothing from ``playwright`` at runtime — it drives an injected,
duck-typed page (a ``.video`` object with async ``path()`` / ``save_as()``, plus async
``close()``), so it is unit-testable with a fake and the core stays vendor-free.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from walkthru.core.schema import AssetRef

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Browser, BrowserContext, Page

#: Playwright's screencast default container.
DEFAULT_VIDEO_MIME = "video/webm"


class RecorderError(RuntimeError):
    """The recorder could not produce a video (e.g. the page was not set up for recording)."""


class RecorderStateError(RecorderError):
    """``start`` / ``stop`` were called out of order (e.g. ``stop`` before ``start``)."""


class PlaywrightRecorder:
    """A :class:`~walkthru.ports.Recorder` backed by Playwright's context-level screencast.

    Args:
        page: a Playwright ``Page`` whose context was created with ``record_video_dir`` set
            (injected, duck-typed — see the module docstring and :func:`new_recording_page`).
        save_as: optional stable path to write the finished video to; when omitted, the returned
            :class:`~walkthru.core.schema.AssetRef` points at the path Playwright chose.
        mime: MIME type recorded on the returned asset (Playwright screencast is WebM).
    """

    def __init__(
        self,
        page: "Page",
        *,
        save_as: Optional[Union[str, Path]] = None,
        mime: str = DEFAULT_VIDEO_MIME,
    ):
        self._page = page
        self._save_as = Path(save_as) if save_as is not None else None
        self._mime = mime
        self._started = False
        self._stopped = False

    async def start(self) -> None:
        if self._started:
            raise RecorderStateError("recorder already started")
        self._started = True

    async def stop(self) -> AssetRef:
        if not self._started:
            raise RecorderStateError("recorder.stop() called before start()")
        if self._stopped:
            raise RecorderStateError("recorder already stopped")
        self._stopped = True

        video = getattr(self._page, "video", None)
        if video is None:
            raise RecorderError(
                "page has no video to save — create its context with record_video_dir set "
                "(see walkthru.adapters.playwright.new_recording_page)"
            )

        # Closing the page is what flushes the screencast to disk.
        await self._page.close()

        if self._save_as is not None:
            self._save_as.parent.mkdir(parents=True, exist_ok=True)
            await video.save_as(str(self._save_as))
            uri = str(self._save_as)
        else:
            uri = str(await video.path())
        return AssetRef(uri=uri, mime=self._mime)


async def new_recording_page(
    browser: "Browser",
    *,
    record_video_dir: Union[str, Path],
    record_video_size: Optional[dict] = None,
    **context_kwargs: Any,
) -> "tuple[BrowserContext, Page]":
    """Create a screencast-recording context + page, returning ``(context, page)``.

    A thin convenience over ``browser.new_context(record_video_dir=…)`` that encodes the
    non-obvious fact that Playwright records at the *context* level. Duck-typed on ``browser`` (no
    ``playwright`` import); the real browser comes from ``playwright.async_api``. Feed the returned
    ``page`` to :class:`PlaywrightRecorder`.
    """
    kwargs: dict[str, Any] = {
        "record_video_dir": str(record_video_dir),
        **context_kwargs,
    }
    if record_video_size is not None:
        kwargs["record_video_size"] = record_video_size
    context = await browser.new_context(**kwargs)
    page = await context.new_page()
    return context, page
