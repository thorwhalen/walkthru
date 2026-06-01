"""WebVTT captions derived from the narration track.

Narration is timed, editable text anchored to steps; once the timeline is composed to absolute
time, captions fall out almost for free (Report 01 §D.2). This exporter is the web-native default;
SRT is deliberately not implemented until a real need appears (YAGNI).
"""

from __future__ import annotations

from walkthru.core.schema import DemoDocument
from walkthru.core.timeline import resolve_timeline


def _timestamp(ms: int) -> str:
    """Format milliseconds as a WebVTT timestamp ``HH:MM:SS.mmm``."""
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}.{millis:03d}"


def narration_to_webvtt(document: DemoDocument) -> str:
    """Render the narration track as a WebVTT caption document.

    Cue start/end come from the resolved (absolute) timeline; cues are emitted in time order.
    Returns a complete ``.vtt`` document (trailing newline included).
    """
    timeline = resolve_timeline(document)
    segments = sorted(timeline.narration, key=lambda r: (r.start_ms, r.end_ms))

    lines = ["WEBVTT", ""]
    for index, segment in enumerate(segments, start=1):
        lines.append(str(index))
        lines.append(f"{_timestamp(segment.start_ms)} --> {_timestamp(segment.end_ms)}")
        lines.append(segment.text)
        lines.append("")

    return "\n".join(lines) + "\n"
