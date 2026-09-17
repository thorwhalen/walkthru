"""Pure geometry and time-slicing for the GIF render target — no ffmpeg, no I/O.

The whole of the camera's meaning lives here, so it is testable without a video file:

* :func:`camera_segments` slices the timeline at each camera keyframe, producing one
  segment per constant-camera interval.
* :func:`crop_box` turns a keyframe's focus rect and zoom into integer pixel bounds,
  corrected to the output aspect ratio and clamped inside the frame. Correcting the
  aspect here rather than in ffmpeg is what lets every segment concatenate: a GIF's
  frames must all be the same size.
* :func:`gif_filtergraph` writes the ffmpeg ``-filter_complex`` string.

>>> crop_box(None, 1.0, frame_w=1280, frame_h=720, aspect=16 / 9)
(0, 0, 1280, 720)
>>> crop_box(None, 2.0, frame_w=1280, frame_h=720, aspect=16 / 9)
(320, 180, 640, 360)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from walkthru.core.schema import Rect
from walkthru.core.timeline import Timeline

__all__ = [
    "CameraSegment",
    "camera_segments",
    "crop_box",
    "gif_filtergraph",
]


@dataclass(frozen=True)
class CameraSegment:
    """A stretch of video over which the camera is constant."""

    start_ms: int
    end_ms: int
    rect: Optional[Rect] = None
    zoom: float = 1.0

    @property
    def duration_ms(self) -> int:
        return self.end_ms - self.start_ms


def camera_segments(
    timeline: Timeline, *, total_ms: int, min_segment_ms: int = 80
) -> tuple[CameraSegment, ...]:
    """Slice ``total_ms`` at each camera keyframe into constant-camera segments.

    With no keyframes the whole video is one full-frame segment -- the honest default,
    not a stub: a demo that does not move the camera renders exactly as recorded.

    Segments shorter than ``min_segment_ms`` are dropped: below a few frames a cut reads
    as a glitch rather than as a move.

    >>> from walkthru.core.timeline import Timeline
    >>> empty = Timeline(steps=(), cues=(), narration=(), camera=(), total_ms=0)
    >>> camera_segments(empty, total_ms=4000)
    (CameraSegment(start_ms=0, end_ms=4000, rect=None, zoom=1.0),)
    """
    keys = sorted(getattr(timeline, "camera", ()) or (), key=lambda c: c.at_ms)
    if not keys:
        return (CameraSegment(0, total_ms),)

    segments: list[CameraSegment] = []
    if keys[0].at_ms > 0:
        segments.append(CameraSegment(0, keys[0].at_ms))
    for i, key in enumerate(keys):
        end = keys[i + 1].at_ms if i + 1 < len(keys) else total_ms
        segments.append(
            CameraSegment(key.at_ms, end, key.keyframe.focus, key.keyframe.zoom or 1.0)
        )
    return tuple(
        s for s in segments if s.duration_ms >= min_segment_ms and s.start_ms < total_ms
    )


def crop_box(
    rect: Optional[Rect],
    zoom: float,
    *,
    frame_w: int,
    frame_h: int,
    aspect: float,
) -> tuple[int, int, int, int]:
    """``(x, y, w, h)`` in whole pixels for one camera state.

    ``rect`` is the region to focus on (``None`` means the whole frame, from which
    ``zoom`` crops centrally). The box is widened or heightened to match ``aspect``,
    clamped inside the frame, and rounded to even numbers -- odd dimensions break
    several encoders.

    >>> crop_box(Rect(x=100, y=100, width=200, height=200), 1.0,
    ...          frame_w=1000, frame_h=1000, aspect=1.0)
    (100, 100, 200, 200)
    >>> x, y, w, h = crop_box(Rect(x=0, y=0, width=100, height=100), 1.0,
    ...                       frame_w=1000, frame_h=1000, aspect=2.0)
    >>> (w, h)  # widened to 2:1, still inside the frame
    (200, 100)
    """
    zoom = max(float(zoom or 1.0), 1e-6)

    if rect is None:
        w = frame_w / zoom
        h = frame_h / zoom
        cx, cy = frame_w / 2, frame_h / 2
    else:
        w = float(rect.width) / zoom
        h = float(rect.height) / zoom
        cx = float(rect.x) + float(rect.width) / 2
        cy = float(rect.y) + float(rect.height) / 2

    # Match the output aspect by growing the short side, never by cropping content away.
    if w / h < aspect:
        w = h * aspect
    else:
        h = w / aspect

    # Never ask for more than the frame has.
    if w > frame_w:
        w, h = float(frame_w), frame_w / aspect
    if h > frame_h:
        h, w = float(frame_h), frame_h * aspect

    x = min(max(cx - w / 2, 0.0), frame_w - w)
    y = min(max(cy - h / 2, 0.0), frame_h - h)

    even = lambda v: int(v) - (int(v) % 2)  # noqa: E731
    return even(x), even(y), even(w), even(h)


def gif_filtergraph(
    segments: Sequence[CameraSegment],
    *,
    frame_w: int,
    frame_h: int,
    out_width: int,
    out_height: int,
    fps: int = 12,
    dither: str = "bayer:bayer_scale=5",
    max_colors: int = 128,
) -> str:
    """The ffmpeg ``-filter_complex`` that crops each segment, concatenates and palettizes.

    Two-pass palette generation (``palettegen`` then ``paletteuse``) is what separates a
    GIF that reads as a screen recording from one that reads as mud; ``stats_mode=diff``
    spends the palette on what moves.

    >>> g = gif_filtergraph([CameraSegment(0, 1000)], frame_w=800, frame_h=600,
    ...                     out_width=800, out_height=600)
    >>> "palettegen" in g and "concat=n=1" in g
    True
    """
    if not segments:
        raise ValueError("no camera segments to render")

    aspect = out_width / out_height
    parts: list[str] = []
    labels: list[str] = []
    for i, seg in enumerate(segments):
        x, y, w, h = crop_box(
            seg.rect, seg.zoom, frame_w=frame_w, frame_h=frame_h, aspect=aspect
        )
        label = f"v{i}"
        labels.append(f"[{label}]")
        parts.append(
            f"[0:v]trim={seg.start_ms / 1000:.3f}:{seg.end_ms / 1000:.3f},"
            f"setpts=PTS-STARTPTS,"
            f"crop={w}:{h}:{x}:{y},"
            # setsar=1 is not cosmetic: cropping different rects gives each segment a
            # different sample aspect ratio, and concat refuses inputs whose SAR differs.
            f"scale={out_width}:{out_height}:flags=lanczos,setsar=1[{label}]"
        )
    parts.append(f"{''.join(labels)}concat=n={len(segments)}:v=1:a=0[cat]")
    parts.append(f"[cat]fps={fps},split[pal][use]")
    parts.append(f"[pal]palettegen=max_colors={max_colors}:stats_mode=diff[p]")
    parts.append(f"[use][p]paletteuse=dither={dither}:diff_mode=rectangle[out]")
    return ";".join(parts)
