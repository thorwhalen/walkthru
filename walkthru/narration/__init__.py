"""Narration realization, pacing, and assembly — author segment *texts*, get timed, voiced audio.

The narration track stores editable **text** as the source of truth; audio and timing are
regenerable (the Descript model). This subpackage is the build-time machinery that realizes that
text, in three composable, vendor-free pieces:

* :func:`~walkthru.narration.realize.realize_narration` — synthesize each segment and write back its
  measured duration + audio reference (the "duration-from-TTS" loop). Because every segment is
  synthesized and measured independently, the beat boundaries fall straight out of
  :func:`~walkthru.core.timeline.resolve_timeline` with no alignment math.
* :func:`~walkthru.narration.pace.pace_steps_to_narration` — an optional, pure policy that holds a
  step on screen for at least as long as its narration (narration-led pacing). Narration stays an
  *independent* track by default (``DECISIONS.md`` §D8).
* :func:`~walkthru.narration.assemble.assemble_narration_audio` — place each clip at its absolute
  timeline offset (silence for the gaps) into one mux-ready track, via an injected assembler.

Everything here imports only the core and the :class:`~walkthru.ports.Synthesizer` port, and the
audio assembler is an injected seam — so the loop is unit-testable with fakes and pulls in no media
stack. The concrete ElevenLabs synthesizer lives in :mod:`walkthru.adapters.synth`, behind the
ports firewall.
"""

from walkthru.narration.assemble import (
    AudioAssembler,
    AudioResolver,
    Slot,
    assemble_narration_audio,
    narration_slots,
)
from walkthru.narration.pace import StepPacing, pace_steps_to_narration
from walkthru.narration.realize import (
    DurationProbe,
    RealizedNarration,
    realize_narration,
)

__all__ = [
    "realize_narration",
    "RealizedNarration",
    "DurationProbe",
    "pace_steps_to_narration",
    "StepPacing",
    "assemble_narration_audio",
    "narration_slots",
    "AudioResolver",
    "AudioAssembler",
    "Slot",
]
