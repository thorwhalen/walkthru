"""Realize a Demo Document's narration: synthesize each segment and time it from its own audio.

The narration track stores *text* as the source of truth (the Descript model); audio and timing are
regenerable. :func:`realize_narration` is the build-time loop that turns authored segment texts into
timed, voiced narration: synthesize each :class:`~walkthru.core.schema.NarrationSegment`, measure the
real clip duration, and write both back (``anchor.duration_ms`` ← measured, ``audio_ref`` ← the clip).

Because each segment is synthesized and measured independently, beat boundaries fall straight out of
:func:`~walkthru.core.timeline.resolve_timeline` with no alignment math — segmented narration that
"lands on its words" by construction. Synthesis and measurement are injected (the
:class:`~walkthru.ports.Synthesizer` port and a duration probe), so this module stays vendor-free and
the loop is unit-testable with fakes; the real ElevenLabs path is :mod:`walkthru.adapters.synth`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from walkthru.core.schema import AssetRef, DemoDocument, NarrationSegment
from walkthru.ports import Synthesizer

#: Measure a synthesized clip's duration in **milliseconds** (e.g. ffprobe). Injected so the realize
#: loop needs no media stack; the default lives in :mod:`walkthru.adapters.synth` (``mixing_duration_ms``).
DurationProbe = Callable[[AssetRef], int]

#: Optional per-segment progress callback ``(segment, asset, duration_ms)`` — for logging/checkpoints.
SegmentCallback = Callable[[NarrationSegment, AssetRef, int], None]


@dataclass(frozen=True)
class RealizedNarration:
    """The result of realizing a document's narration.

    ``document`` is a *new*, timed :class:`~walkthru.core.schema.DemoDocument` (the input is never
    mutated): every narration segment now carries a measured ``anchor.duration_ms`` and an
    ``audio_ref``. ``audio_by_segment`` maps each segment id to its synthesized clip, for downstream
    assembly/mux without re-walking the document.
    """

    document: DemoDocument
    audio_by_segment: dict[str, AssetRef]


async def realize_narration(
    document: DemoDocument,
    *,
    synth: Synthesizer,
    measure_ms: DurationProbe,
    on_segment: Optional[SegmentCallback] = None,
) -> RealizedNarration:
    """Synthesize and time every narration segment in ``document``.

    For each :class:`~walkthru.core.schema.NarrationSegment`, in track order: synthesize its ``text``
    via ``synth``, measure the clip with ``measure_ms``, and produce an updated segment whose
    ``anchor.duration_ms`` equals the measured length and whose ``audio_ref`` points at the clip. The
    returned :class:`RealizedNarration` wraps a new document — the input is left untouched, so the
    authored text remains the immutable source of truth.

    Args:
        document: the Demo Document whose narration texts to realize.
        synth: the text-to-speech port (e.g. :class:`~walkthru.adapters.synth.MixingSynthesizer`).
        measure_ms: returns a clip's duration in milliseconds (e.g. ``mixing_duration_ms``).
        on_segment: optional progress callback invoked ``(segment, asset, duration_ms)`` per realized
            segment — for logging or human-in-the-loop checkpoints; it must not mutate its arguments.

    Returns:
        A :class:`RealizedNarration` with the timed document and the per-segment audio map.
    """
    audio_by_segment: dict[str, AssetRef] = {}
    realized_segments: list[NarrationSegment] = []
    for segment in document.tracks.narration:
        asset = await synth.say(segment.text)
        duration_ms = measure_ms(asset)
        realized = segment.model_copy(
            update={
                "anchor": segment.anchor.model_copy(
                    update={"duration_ms": duration_ms}
                ),
                "audio_ref": asset,
            }
        )
        realized_segments.append(realized)
        audio_by_segment[segment.id] = asset
        if on_segment is not None:
            on_segment(realized, asset, duration_ms)

    new_tracks = document.tracks.model_copy(update={"narration": realized_segments})
    new_document = document.model_copy(update={"tracks": new_tracks})
    return RealizedNarration(document=new_document, audio_by_segment=audio_by_segment)
