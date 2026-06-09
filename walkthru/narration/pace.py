"""Optionally pace steps to their narration — hold a beat at least as long as it is spoken.

By design narration is an *independent* track: a :class:`~walkthru.core.schema.NarrationSegment`'s
``anchor.duration_ms`` does not change the step it is anchored to (``DECISIONS.md`` §D8). That is the
right default for a tour whose visual beats are authored to the action. But for a *narration-led*
storyboard — where each beat should stay on screen for as long as its line is spoken — this module
provides a small, **pure** policy that stretches a step's ``timing.duration_ms`` to cover the
narration anchored to it. It changes only step durations; it adds no schema, reorders nothing, and
never touches the narration track (so it composes cleanly after
:func:`~walkthru.narration.realize.realize_narration`).
"""

from __future__ import annotations

from typing import Literal

from walkthru.core.schema import DemoDocument, NarrationSegment, Step

#: How a step's duration relates to the narration anchored to it:
#:
#: * ``"keep"`` — leave step durations unchanged (narration is a fully independent track).
#: * ``"max"`` — hold for the longer of the authored visual duration and the narration extent.
#: * ``"narration"`` — set the step duration to exactly its narration extent (when it has any).
StepPacing = Literal["keep", "max", "narration"]


def _narration_extent_ms(step_id: str, narration: list[NarrationSegment]) -> int:
    """The end (relative to the step's start) of the last narration anchored to ``step_id``."""
    return max(
        (
            seg.anchor.local_offset_ms + seg.anchor.duration_ms
            for seg in narration
            if seg.anchor.step_id == step_id
        ),
        default=0,
    )


def pace_steps_to_narration(
    document: DemoDocument, *, policy: StepPacing = "max"
) -> DemoDocument:
    """Return a new document whose step durations are paced to their narration, per ``policy``.

    For each step, the narration *extent* is ``max(local_offset_ms + duration_ms)`` over the segments
    anchored to it (``0`` if none). ``policy`` then sets the step's ``timing.duration_ms``:

    * ``"keep"`` returns the document unchanged;
    * ``"max"`` raises a step to ``max(current, extent)`` so it never *shrinks* below its visual beat;
    * ``"narration"`` sets it to ``extent`` exactly (steps with no narration are left as-is).

    The input is never mutated. Pure and side-effect-free — safe to run before
    :func:`~walkthru.core.timeline.resolve_timeline`, which then recomposes absolute time.
    """
    if policy == "keep":
        return document
    narration = list(document.tracks.narration)

    def _repaced(step: Step) -> Step:
        extent = _narration_extent_ms(step.id, narration)
        if extent == 0:
            return step
        new_duration = (
            extent if policy == "narration" else max(step.timing.duration_ms, extent)
        )
        if new_duration == step.timing.duration_ms:
            return step
        new_timing = step.timing.model_copy(update={"duration_ms": new_duration})
        return step.model_copy(update={"timing": new_timing})

    new_sections = [
        section.model_copy(update={"steps": [_repaced(s) for s in section.steps]})
        for section in document.sections
    ]
    return document.model_copy(update={"sections": new_sections})
