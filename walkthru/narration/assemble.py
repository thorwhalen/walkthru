"""Assemble the narration track into one audio file, each clip at its absolute timeline offset.

Once :func:`~walkthru.narration.realize.realize_narration` has voiced and timed the narration and
:func:`~walkthru.core.timeline.resolve_timeline` has placed each segment on absolute time, the
narration audio is just a sequence of clips separated by silence. :func:`narration_slots` derives
that ``(clip | None, duration_s)`` slot list **purely** (testable with no media stack), and
:func:`assemble_narration_audio` hands it to an injected assembler (default
:func:`mixing.assemble_audio_track`, imported lazily) — the same injected-seam idiom as the reelee
render target — to write one mux-ready track.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Optional, Union

from walkthru.core.schema import AssetRef
from walkthru.core.timeline import Timeline

#: Resolve a narration ``audio_ref`` to a local clip path, or ``None`` (a silent slot of that length).
AudioResolver = Callable[[Optional[AssetRef]], Optional[Path]]
#: Assemble ``(clip | None, duration_s)`` slots into one audio file (``mixing.assemble_audio_track`` shape).
AudioAssembler = Callable[..., Optional[Path]]
#: One timeline slot: a clip (or ``None`` for silence) and how long it occupies, in **seconds**.
Slot = tuple[Optional[Path], float]


def _asset_to_path(asset: Optional[AssetRef]) -> Optional[Path]:
    """Default resolver: a segment's ``audio_ref`` uri as a local path (``None`` if unset)."""
    return Path(asset.uri) if asset is not None else None


def narration_slots(
    timeline: Timeline,
    *,
    resolve_audio: AudioResolver = _asset_to_path,
    total_ms: Optional[int] = None,
) -> list[Slot]:
    """Derive the narration track's ``(clip | None, duration_s)`` slots from a resolved timeline.

    Narration segments are placed at their absolute ``start_ms``; the gaps between them (and the
    lead-in before the first) become silence slots, and a trailing silence pads out to ``total_ms``
    (default: the timeline's own ``total_ms``) so the assembled track spans the whole film. Each
    clip's slot length is its own ``end_ms - start_ms`` — the measured TTS duration after
    :func:`~walkthru.narration.realize.realize_narration` — so clips are never trimmed.

    Raises:
        ValueError: if two narration segments overlap. The slot model is sequential; overlapping
            narration would need an audio *mixing* layer, which is a renderer concern, not this track.
    """
    segments = sorted(timeline.narration, key=lambda r: (r.start_ms, r.end_ms))
    slots: list[Slot] = []
    cursor = 0
    for seg in segments:
        if seg.start_ms < cursor:
            raise ValueError(
                f"narration segments overlap: {seg.segment_id!r} starts at {seg.start_ms}ms, "
                f"before the previous segment ends at {cursor}ms"
            )
        if seg.start_ms > cursor:
            slots.append((None, (seg.start_ms - cursor) / 1000.0))
        slots.append(
            (resolve_audio(seg.segment.audio_ref), (seg.end_ms - seg.start_ms) / 1000.0)
        )
        cursor = seg.end_ms
    end_ms = timeline.total_ms if total_ms is None else total_ms
    if end_ms > cursor:
        slots.append((None, (end_ms - cursor) / 1000.0))
    return slots


def _default_assembler() -> AudioAssembler:
    from mixing import assemble_audio_track

    return assemble_audio_track


def assemble_narration_audio(
    timeline: Timeline,
    output: Union[str, Path],
    *,
    resolve_audio: AudioResolver = _asset_to_path,
    total_ms: Optional[int] = None,
    assembler: Optional[AudioAssembler] = None,
) -> Optional[Path]:
    """Assemble the narration track into one audio file at ``output`` (or ``None`` if all silent).

    Derives the slots with :func:`narration_slots`, then hands them to ``assembler`` (default
    :func:`mixing.assemble_audio_track`, imported lazily) — so this runs with a stub and no
    ffmpeg/MoviePy. Returns the written path, or ``None`` when the track carries no audio at all
    (every slot is silence — nothing to mux).
    """
    slots = narration_slots(timeline, resolve_audio=resolve_audio, total_ms=total_ms)
    if not any(clip is not None for clip, _ in slots):
        return None
    assembler = assembler or _default_assembler()
    return assembler(slots, output=Path(output))
