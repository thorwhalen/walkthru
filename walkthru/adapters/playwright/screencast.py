"""A high-quality screen recording, from Chrome DevTools' screencast, as a constant-rate mp4.

:class:`~walkthru.adapters.playwright.recorder.PlaywrightRecorder` films through Playwright's
``record_video_dir``: WebM at a fixed, low bitrate, so small interface text smears, and with no
clock a caller can line anything else up against. A narrated tour needs both: text that reads,
and the moment each step began *in the video's own time*, so narration and cuts land on it.

:class:`CdpScreencastRecorder` asks the browser for its frames directly
(``Page.startScreencast``). Each frame arrives as a JPEG at the page's **device** resolution
(a phone viewport at ``device_scale_factor=2.5`` films at 1080×1920; launch Chrome with
``--force-device-scale-factor`` to match, see :func:`screencast_launch_args`) with a wall-clock
timestamp. Frames only come when something on screen changes, so the recording is variable-rate
by nature; :meth:`CdpScreencastRecorder.stop` turns it into a constant-rate H.264 mp4: for each
output frame it picks the latest screencast frame at or before that moment (:func:`cfr_schedule`)
and pipes the result to ffmpeg. (Not an ``ffconcat`` list with per-image durations: the concat
demuxer stretches an image shorter than its own default frame duration, and a recording whose
frames come at 60 per second comes out seconds longer than it was, drifting every cut.)

**The clock.** Frame timestamps are wall-clock seconds, the same clock as :func:`time.time`, so a
wall-clock mark taken in Python (:class:`~walkthru.observers.marks.StepMarks`) maps into the video
with :meth:`~CdpScreencastRecorder.video_time`. Video time 0 is the moment recording started; a
still screen sends no frames, so the first frame is held back to it.

Chromium only (DevTools protocol). Like its siblings, nothing here imports ``playwright`` at
runtime: the page and its CDP session are duck-typed, and ffmpeg is an injected ``runner``, so the
pure parts (:func:`cfr_schedule`, :func:`encode_argv`) are tested without a browser.
"""

from __future__ import annotations

import asyncio
import base64
import re
import subprocess
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable, Optional, Sequence, Union

from walkthru.adapters.gif.render_target import check_ffmpeg
from walkthru.adapters.playwright.recorder import RecorderError, RecorderStateError
from walkthru.core.schema import AssetRef

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page

__all__ = [
    "CdpScreencastRecorder",
    "Frame",
    "cfr_schedule",
    "encode_argv",
    "screencast_launch_args",
]

DEFAULT_FPS = 30
#: The names this recorder gives its frames — the only files it ever deletes.
_FRAME_NAME = re.compile(r"\d{6}\.jpg")
#: JPEG quality of each screencast frame. 92 keeps small interface text crisp.
DEFAULT_QUALITY = 92
#: x264 constant-rate factor for the encoded mp4 (lower is better; 16 is near-transparent).
DEFAULT_CRF = 16

#: ``(wall-clock timestamp in seconds, path to the frame's JPEG)``.
Frame = tuple[float, Path]


def screencast_launch_args(device_scale_factor: float = 1.0) -> list[str]:
    """Chrome flags so screencast frames come at device pixels, not CSS pixels.

    Headless Chrome films at CSS-pixel size whatever the context's ``device_scale_factor``;
    forcing the scale factor at launch is what makes a phone viewport film at phone resolution.

    >>> screencast_launch_args(2.5)
    ['--force-device-scale-factor=2.5']
    >>> screencast_launch_args()
    []
    """
    if device_scale_factor == 1.0:
        return []
    return [f"--force-device-scale-factor={device_scale_factor:g}"]


def cfr_schedule(
    times: Sequence[float], *, start: float, end: float, fps: int = DEFAULT_FPS
) -> list[int]:
    """For each constant-rate output frame, the index of the screencast frame on screen then.

    Output frame ``k`` is the moment ``start + k / fps``; it shows the latest frame whose
    timestamp is at or before that moment (the first frame before it has arrived: a still screen
    sends nothing, so the first frame *is* what was on screen). The count is
    ``round((end - start) * fps)``, so the video is exactly as long as the recording was.

    >>> cfr_schedule([10.0, 10.05, 10.5], start=10.0, end=10.6, fps=10)
    [0, 1, 1, 1, 1, 2]
    >>> cfr_schedule([10.2], start=10.0, end=10.3, fps=10)  # held back to the start
    [0, 0, 0]
    """
    if not times:
        raise RecorderError("no screencast frames were received")
    n = max(1, round((end - start) * fps))
    out, j = [], 0
    for k in range(n):
        t = start + k / fps
        while j + 1 < len(times) and times[j + 1] <= t:
            j += 1
        out.append(j)
    return out


def encode_argv(
    out_path: Union[str, Path],
    *,
    fps: int = DEFAULT_FPS,
    crf: int = DEFAULT_CRF,
    ffmpeg: str = "ffmpeg",
) -> list[str]:
    """ffmpeg argv: JPEG frames on stdin at ``fps`` → an even-sized, faststart H.264 mp4.

    >>> argv = encode_argv("out.mp4", fps=30)
    >>> argv[argv.index("-f") + 1], argv[argv.index("-framerate") + 1], argv[-1]
    ('image2pipe', '30', 'out.mp4')
    """
    return [
        ffmpeg, "-v", "error", "-y",
        "-f", "image2pipe", "-framerate", str(fps), "-c:v", "mjpeg", "-i", "-",
        # JPEG frames are full-range (yuvj420p); players expect TV range, and a
        # full-range flag is mis-shown or refused by Safari/iOS and uploaders
        "-vf", "scale=trunc(iw/2)*2:trunc(ih/2)*2:out_range=tv,format=yuv420p",
        "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-r", str(fps),
        "-movflags", "+faststart", str(out_path),
    ]  # fmt: skip


def _pipe_frames(argv: Sequence[str], frames: Iterable[bytes]) -> None:
    """Run ffmpeg, writing each frame's bytes to its stdin."""
    proc = subprocess.Popen(list(argv), stdin=subprocess.PIPE)
    try:
        for data in frames:
            proc.stdin.write(data)
    finally:
        proc.stdin.close()
    if proc.wait() != 0:
        raise RecorderError(f"ffmpeg failed encoding the screencast: {' '.join(argv)}")


class CdpScreencastRecorder:
    """A :class:`~walkthru.ports.Recorder` backed by Chrome DevTools' ``Page.startScreencast``.

    Args:
        page: a Playwright ``Page`` in Chromium (duck-typed: ``page.context.new_cdp_session``).
        save_as: where the finished mp4 goes.
        frames_dir: where frames are written while recording (default: ``<save_as stem>_frames``
            beside it). Only files named like its frames (``000123.jpg``) are ever deleted there.
        fps: frame rate of the encoded mp4.
        quality: JPEG quality of each frame.
        max_size: ``(width, height)`` cap on frame size, in device pixels (default: uncapped).
        crf: x264 quality of the encoded mp4.
        encoder: ``(argv, frame_bytes_iterable) -> None``, runs ffmpeg (injected for tests).
        keep_frames: keep the frame JPEGs after encoding (default: delete them).
        check_ffmpeg: fail at ``start()`` when ffmpeg is not on PATH (default ``True``).
        clock: wall-clock seconds, the frames' clock (injected for tests).
    """

    def __init__(
        self,
        page: "Page",
        *,
        save_as: Union[str, Path],
        frames_dir: Optional[Union[str, Path]] = None,
        fps: int = DEFAULT_FPS,
        quality: int = DEFAULT_QUALITY,
        max_size: Optional[tuple[int, int]] = None,
        crf: int = DEFAULT_CRF,
        encoder: Callable[[Sequence[str], Iterable[bytes]], Any] = _pipe_frames,
        clock: Callable[[], float] = time.time,
        keep_frames: bool = False,
        check_ffmpeg: bool = True,
    ):
        self._page = page
        self._save_as = Path(save_as)
        self._frames_dir = (
            Path(frames_dir)
            if frames_dir is not None
            else self._save_as.with_name(self._save_as.stem + "_frames")
        )
        self._fps = fps
        self._quality = quality
        self._max_size = max_size
        self._crf = crf
        self._encoder = encoder
        self._keep_frames = keep_frames
        self._check_ffmpeg = check_ffmpeg
        self._start_ts: Optional[float] = None
        self._clock = clock
        self._cdp: Any = None
        self._frames: list[Frame] = []
        self._acks: set[asyncio.Future] = set()
        self._started = False
        self._stopped = False

    @property
    def frames(self) -> list[Frame]:
        """The frames received so far, in arrival order."""
        return list(self._frames)

    @property
    def origin(self) -> float:
        """The wall-clock time of video time 0 (when recording started)."""
        if self._start_ts is None:
            raise RecorderStateError("the recording has not started, so it has no origin")
        return self._start_ts

    def video_time(self, wall_ts: float) -> float:
        """Seconds into the video at wall-clock ``wall_ts`` (0 before it started)."""
        return max(0.0, wall_ts - self.origin)

    async def start(self) -> None:
        if self._started:
            raise RecorderStateError("recorder already started")
        if self._check_ffmpeg:
            check_ffmpeg()  # found now, not after a four-minute take
        self._started = True
        self._frames_dir.mkdir(parents=True, exist_ok=True)
        for stale in self._frames_dir.iterdir():  # only frames this recorder writes
            if _FRAME_NAME.fullmatch(stale.name):
                stale.unlink()
        self._cdp = await self._page.context.new_cdp_session(self._page)
        self._cdp.on("Page.screencastFrame", self._on_frame)
        params: dict[str, Any] = {
            "format": "jpeg",
            "quality": self._quality,
            "everyNthFrame": 1,
        }
        if self._max_size is not None:
            params["maxWidth"], params["maxHeight"] = self._max_size
        await self._cdp.send("Page.startScreencast", params)
        self._start_ts = self._clock()

    def _on_frame(self, params: dict) -> None:
        if self._stopped:
            return
        # Acknowledge first: Chrome sends the next frame only once this one is, so
        # anything done before the ack lowers the frame rate under load.
        ack = asyncio.ensure_future(
            self._cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
        )
        self._acks.add(ack)
        ack.add_done_callback(self._acks.discard)
        # ``timestamp`` is optional in the protocol; without it, the arrival time
        # (the same wall clock, a few milliseconds later) is the next best thing.
        ts = (params.get("metadata") or {}).get("timestamp")
        path = self._frames_dir / f"{len(self._frames):06d}.jpg"
        path.write_bytes(base64.b64decode(params["data"]))
        self._frames.append((float(ts) if ts is not None else self._clock(), path))

    async def stop(self) -> AssetRef:
        if not self._started:
            raise RecorderStateError("recorder.stop() called before start()")
        if self._stopped:
            raise RecorderStateError("recorder already stopped")
        end_ts = self._clock()
        self._stopped = True
        try:
            await self._cdp.send("Page.stopScreencast")
        except Exception:  # noqa: BLE001 — the page may be gone; the frames are not
            pass
        if self._acks:
            await asyncio.gather(*self._acks, return_exceptions=True)
        schedule = cfr_schedule(
            [ts for ts, _ in self._frames], start=self.origin, end=end_ts, fps=self._fps
        )
        self._save_as.parent.mkdir(parents=True, exist_ok=True)
        paths = [path for _, path in self._frames]
        self._encoder(
            encode_argv(self._save_as, fps=self._fps, crf=self._crf),
            (paths[i].read_bytes() for i in schedule),
        )
        if not self._keep_frames:  # minutes of motion is gigabytes of JPEG
            for path in paths:
                path.unlink(missing_ok=True)
        return AssetRef(uri=str(self._save_as), mime="video/mp4")
