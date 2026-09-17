"""The GIF ``RenderTarget`` — a recorded screencast plus the camera track, as an animated GIF.

PLAN §6 kept secondary render targets for "when real". A README that has to *show* an
interactive report is when it became real: a GIF plays inline on GitHub and PyPI, where a
video does not.

The split follows the reelee target's idiom -- everything that carries meaning is a pure
function in :mod:`~walkthru.adapters.gif.geometry`, and this module is the thin driver that
shells out. ``runner`` and ``prober`` are injected, so the whole path is testable without
ffmpeg installed.

ffmpeg is a *system* dependency, not a Python one, so there is no extra to install: call
:func:`check_ffmpeg` to get an actionable message instead of a ``FileNotFoundError``.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence, Union

from walkthru.adapters.gif.geometry import (
    CameraSegment,
    camera_segments,
    gif_filtergraph,
)
from walkthru.core.schema import AssetRef, DemoDocument
from walkthru.core.timeline import resolve_timeline

__all__ = [
    "FfmpegMissingError",
    "GifRenderError",
    "VideoInfo",
    "check_ffmpeg",
    "probe_video",
    "video_to_gif",
    "GifRenderTarget",
]

Runner = Callable[..., Any]


class GifRenderError(RuntimeError):
    """ffmpeg or ffprobe failed, or produced nothing."""


class FfmpegMissingError(GifRenderError):
    """ffmpeg is not on PATH."""


@dataclass(frozen=True)
class VideoInfo:
    """What the renderer needs to know about the source screencast."""

    width: int
    height: int
    duration_ms: int


def check_ffmpeg(*, ffmpeg: str = "ffmpeg", ffprobe: str = "ffprobe") -> None:
    """Raise :class:`FfmpegMissingError` with an actionable message if the tools are absent.

    >>> check_ffmpeg(ffmpeg="definitely-not-a-real-binary")
    Traceback (most recent call last):
    ...
    walkthru.adapters.gif.render_target.FfmpegMissingError: ...
    """
    missing = [name for name in (ffmpeg, ffprobe) if shutil.which(name) is None]
    if missing:
        raise FfmpegMissingError(
            f"{', '.join(missing)} not found on PATH. Install ffmpeg: "
            "`brew install ffmpeg` (macOS), `apt install ffmpeg` (Debian/Ubuntu), "
            "or see https://ffmpeg.org/download.html"
        )


def _run(runner: Runner, argv: Sequence[str]) -> subprocess.CompletedProcess:
    result = runner(list(argv), capture_output=True, text=True)
    if getattr(result, "returncode", 0) != 0:
        tail = (getattr(result, "stderr", "") or "").strip().splitlines()[-6:]
        raise GifRenderError(f"{argv[0]} failed:\n" + "\n".join(tail))
    return result


def probe_video(
    video: Union[str, Path],
    *,
    ffprobe: str = "ffprobe",
    runner: Runner = subprocess.run,
) -> VideoInfo:
    """Frame size and duration of ``video``, via ffprobe.

    Playwright's WebM screencasts often carry no container duration, so the stream's
    duration is used when present and the format's is the fallback.
    """
    result = _run(
        runner,
        [
            ffprobe,
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=width,height,duration:format=duration",
            "-of",
            "json",
            str(video),
        ],
    )
    data = json.loads(result.stdout)
    stream = (data.get("streams") or [{}])[0]
    duration = stream.get("duration") or (data.get("format") or {}).get("duration")
    if not stream.get("width") or duration is None:
        raise GifRenderError(f"ffprobe could not read dimensions/duration from {video}")
    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        duration_ms=int(float(duration) * 1000),
    )


def video_to_gif(
    video: Union[str, Path],
    out: Union[str, Path],
    *,
    segments: Optional[Sequence[CameraSegment]] = None,
    width: Optional[int] = None,
    fps: int = 12,
    max_colors: int = 128,
    dither: str = "bayer:bayer_scale=5",
    info: Optional[VideoInfo] = None,
    ffmpeg: str = "ffmpeg",
    ffprobe: str = "ffprobe",
    runner: Runner = subprocess.run,
) -> AssetRef:
    """Render ``video`` to an animated GIF at ``out``, applying the camera ``segments``.

    With no ``segments`` the whole video is rendered full-frame. ``width`` defaults to the
    source width; the height follows the source aspect, rounded to an even number.

    ``dither`` is the size lever that matters for screen recordings. The default is right
    for photographic content; for a UI capture -- flat fills, text, few colours -- pass
    ``dither="none"`` and a smaller ``max_colors``: dithering sprays noise across every
    flat region, which is exactly what a GIF cannot compress.
    """
    if info is None:
        info = probe_video(video, ffprobe=ffprobe, runner=runner)
    if segments is None:
        segments = (CameraSegment(0, info.duration_ms),)

    out_width = int(width or info.width)
    out_height = int(out_width * info.height / info.width)
    out_width -= out_width % 2
    out_height -= out_height % 2

    graph = gif_filtergraph(
        segments,
        frame_w=info.width,
        frame_h=info.height,
        out_width=out_width,
        out_height=out_height,
        fps=fps,
        max_colors=max_colors,
        dither=dither,
    )
    Path(out).parent.mkdir(parents=True, exist_ok=True)
    _run(
        runner,
        [
            ffmpeg,
            "-y",
            "-i",
            str(video),
            "-filter_complex",
            graph,
            "-map",
            "[out]",
            "-loop",
            "0",
            str(out),
        ],
    )
    return AssetRef(uri=str(out), mime="image/gif")


class GifRenderTarget:
    """A :class:`~walkthru.ports.RenderTarget` that emits a GIF of a recorded screencast.

    Unlike the reelee target, which *builds* a film from panels, this one *re-frames* a
    screencast the recorder already produced: the Demo Document supplies the camera track,
    the video supplies the pixels.

    Args:
        video: the screencast to re-frame (typically the ``AssetRef.uri`` a
            :class:`~walkthru.adapters.playwright.PlaywrightRecorder` returned).
        out: where to write the GIF.
        width: output width in pixels; defaults to the source width.
        fps: GIF frame rate. 10-15 reads as smooth for UI motion without bloating the file.
        dither: ffmpeg ``paletteuse`` dither mode. ``"none"`` for UI captures -- see
            :func:`video_to_gif`.
        runner/prober: injected seams for testing (see the module docstring).
    """

    def __init__(
        self,
        video: Union[str, Path],
        out: Union[str, Path],
        *,
        width: Optional[int] = None,
        fps: int = 12,
        max_colors: int = 128,
        dither: str = "bayer:bayer_scale=5",
        min_segment_ms: int = 80,
        ffmpeg: str = "ffmpeg",
        ffprobe: str = "ffprobe",
        runner: Runner = subprocess.run,
    ):
        self._video = video
        self._out = out
        self._width = width
        self._fps = fps
        self._max_colors = max_colors
        self._dither = dither
        self._min_segment_ms = min_segment_ms
        self._ffmpeg = ffmpeg
        self._ffprobe = ffprobe
        self._runner = runner

    async def export(self, artifact: DemoDocument) -> AssetRef:
        """Resolve ``artifact``'s camera track and render the GIF."""
        info = probe_video(self._video, ffprobe=self._ffprobe, runner=self._runner)
        timeline = resolve_timeline(artifact)
        segments = camera_segments(
            timeline,
            total_ms=info.duration_ms,
            min_segment_ms=self._min_segment_ms,
        )
        return video_to_gif(
            self._video,
            self._out,
            segments=segments,
            width=self._width,
            fps=self._fps,
            max_colors=self._max_colors,
            dither=self._dither,
            info=info,
            ffmpeg=self._ffmpeg,
            runner=self._runner,
        )
