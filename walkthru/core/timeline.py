"""Relative-to-absolute time composition over a Demo Document.

The SSOT stores only *relative* durations — each step a local ``durationMs`` (+ optional
``holdAfterMs``), and cues/narration/camera anchored to a ``(stepId, localOffsetMs)`` pair. Global
time is *derived by composition* (Report 02 §A.3), never stored. This module is that derivation:
the single place that turns the relative SSOT into absolute milliseconds for a renderer or
exporter to consume. Keeping it here (pure, dependency-free) means every downstream
:mod:`adapter <walkthru.adapters>` shares one timing model rather than re-deriving it.

The step cursor advances by ``durationMs`` then ``holdAfterMs``: a step occupies
``[start, start + durationMs)`` and the next step starts after the hold. Cues and camera keyframes
anchor at ``step.start + localOffsetMs``; a cue with no ``durationMs`` lasts until its step ends.
Narration spans ``[start + localOffsetMs, + durationMs)``.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass, field

from walkthru.core.schema import (
    CameraKeyframe,
    Cue,
    DemoDocument,
    NarrationSegment,
    Step,
)


@dataclass(frozen=True)
class ResolvedStep:
    """A step placed on the absolute timeline."""

    step_id: str
    kind: str
    start_ms: int
    end_ms: int
    hold_after_ms: int
    step: Step


@dataclass(frozen=True)
class ResolvedCue:
    """A cue placed on the absolute timeline."""

    cue_id: str
    type: str
    start_ms: int
    end_ms: int
    cue: Cue


@dataclass(frozen=True)
class ResolvedNarration:
    """A narration segment placed on the absolute timeline."""

    segment_id: str
    start_ms: int
    end_ms: int
    text: str
    segment: NarrationSegment


@dataclass(frozen=True)
class ResolvedCamera:
    """A camera keyframe placed on the absolute timeline (an instant)."""

    keyframe_id: str
    at_ms: int
    keyframe: CameraKeyframe


@dataclass(frozen=True)
class Timeline:
    """The fully composed, absolute-time view of a Demo Document."""

    steps: tuple[ResolvedStep, ...]
    cues: tuple[ResolvedCue, ...]
    narration: tuple[ResolvedNarration, ...]
    camera: tuple[ResolvedCamera, ...]
    total_ms: int
    _starts: dict[str, ResolvedStep] = field(default_factory=dict, repr=False)

    def step(self, step_id: str) -> ResolvedStep:
        """The resolved step with this id (raises ``KeyError`` if absent)."""
        return self._starts[step_id]


def iter_resolved_steps(document: DemoDocument) -> Iterator[ResolvedStep]:
    """Yield each step with its absolute ``start_ms``/``end_ms``, in document order.

    Lazy by design (per the iterables convention): the aggregate :func:`resolve_timeline`
    materializes this when it needs totals and cross-track lookups.
    """
    cursor = 0
    for section in document.sections:
        for step in section.steps:
            duration = step.timing.duration_ms
            hold = step.timing.hold_after_ms or 0
            start = cursor
            end = start + duration
            yield ResolvedStep(
                step_id=step.id,
                kind=step.kind,
                start_ms=start,
                end_ms=end,
                hold_after_ms=hold,
                step=step,
            )
            cursor = end + hold


def _require_step(
    starts: dict[str, ResolvedStep], step_id: str, what: str
) -> ResolvedStep:
    try:
        return starts[step_id]
    except KeyError:
        raise ValueError(
            f"{what} anchors to unknown step {step_id!r}; known steps: {sorted(starts)}"
        ) from None


def resolve_timeline(document: DemoDocument) -> Timeline:
    """Compose ``document`` into absolute time: steps, cues, narration, and camera.

    Anchors are resolved against step start times; an anchor to a non-existent step is a malformed
    document and raises ``ValueError`` (fail fast rather than silently drop an annotation).
    """
    steps = tuple(iter_resolved_steps(document))
    starts = {rs.step_id: rs for rs in steps}
    total = (steps[-1].end_ms + steps[-1].hold_after_ms) if steps else 0

    cues: list[ResolvedCue] = []
    for cue in document.tracks.cues:
        base = _require_step(starts, cue.anchor.step_id, f"cue {cue.id!r}")
        start = base.start_ms + cue.anchor.local_offset_ms
        end = start + cue.duration_ms if cue.duration_ms is not None else base.end_ms
        cues.append(
            ResolvedCue(
                cue_id=cue.id, type=cue.type, start_ms=start, end_ms=end, cue=cue
            )
        )

    narration: list[ResolvedNarration] = []
    for seg in document.tracks.narration:
        base = _require_step(starts, seg.anchor.step_id, f"narration {seg.id!r}")
        start = base.start_ms + seg.anchor.local_offset_ms
        narration.append(
            ResolvedNarration(
                segment_id=seg.id,
                start_ms=start,
                end_ms=start + seg.anchor.duration_ms,
                text=seg.text,
                segment=seg,
            )
        )

    camera: list[ResolvedCamera] = []
    for keyframe in document.tracks.camera:
        base = _require_step(starts, keyframe.anchor.step_id, f"camera {keyframe.id!r}")
        camera.append(
            ResolvedCamera(
                keyframe_id=keyframe.id,
                at_ms=base.start_ms + keyframe.anchor.local_offset_ms,
                keyframe=keyframe,
            )
        )

    return Timeline(
        steps=steps,
        cues=tuple(cues),
        narration=tuple(narration),
        camera=tuple(camera),
        total_ms=total,
        _starts=starts,
    )
