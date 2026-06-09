"""SRT captions derived from the narration track — the universal-tool-support sibling of WebVTT.

:func:`~walkthru.adapters.export.webvtt.narration_to_webvtt` is the web-native caption default; this
adds SRT, the lowest-common-denominator subtitle format every player, editor, and uploader
understands. The derivation is identical: compose the document onto absolute time and emit one cue
per narration segment, in time order. The only differences from WebVTT are the ``,``-millisecond
separator and the absence of the ``WEBVTT`` header.

(The webvtt module deferred SRT under YAGNI; the storyboard work — videos consumed by editors and
uploaders that expect SRT — is the real need that triggers it.)
"""

from __future__ import annotations

from walkthru.core.schema import DemoDocument
from walkthru.core.timeline import resolve_timeline


def _timestamp(ms: int) -> str:
    """Format milliseconds as an SRT timestamp ``HH:MM:SS,mmm`` (comma separator)."""
    hours, rem = divmod(ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    seconds, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def narration_to_srt(document: DemoDocument) -> str:
    """Render the narration track as an SRT subtitle document.

    Cue start/end come from the resolved (absolute) timeline; cues are emitted in time order, indexed
    from 1. Returns a complete ``.srt`` document (trailing newline included), or an empty string when
    there is no narration.
    """
    timeline = resolve_timeline(document)
    segments = sorted(timeline.narration, key=lambda r: (r.start_ms, r.end_ms))

    blocks = [
        f"{index}\n{_timestamp(seg.start_ms)} --> {_timestamp(seg.end_ms)}\n{seg.text}"
        for index, seg in enumerate(segments, start=1)
    ]
    return ("\n\n".join(blocks) + "\n") if blocks else ""
