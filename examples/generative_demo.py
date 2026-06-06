"""Generative mode — author a Demo Document, then play it.

This is the first of walkthru's two modes. In **generative** mode an author supplies the
Demo Document (commands + cues + narration) and ``play()`` walks it, calling an ``executor``
for each command and emitting a lifecycle event stream. Observers (a logger here; a video
recorder / overlay / narrator in a real run) subscribe to that stream. The *other* mode,
:mod:`capture <capture_demo>`, fills in the *same* document from a human's live actions — see
``examples/capture_demo.py``.

What this script shows:

1. Authoring a Demo Document from the top-level :mod:`walkthru` facade alone — two command
   steps and a title-card beat, with a highlight + callout cue and a narration segment.
2. Playing it with :func:`walkthru.play`, driven by a tiny in-memory ``executor`` and watched
   by a logging :data:`~walkthru.Observer`.
3. The renderer hand-off: the frozen JSON projection (:func:`~walkthru.adapters.export.to_json`)
   a renderer consumes, and WebVTT captions
   (:func:`~walkthru.adapters.export.narration_to_webvtt`) derived from the narration track.

It is **pure core**: nothing here imports a vendor SDK or ecosystem package, so it runs
straight after ``pip install walkthru`` with no optional adapters.

Run it::

    python examples/generative_demo.py
"""

from __future__ import annotations

import asyncio

from walkthru import (
    Anchor,
    Beat,
    CalloutCue,
    Command,
    CommandStep,
    DemoDocument,
    Event,
    HighlightCue,
    Locator,
    Meta,
    NarrationAnchor,
    NarrationSegment,
    Outcome,
    Section,
    Target,
    Timing,
    Tracks,
    play,
)
from walkthru.adapters.export import narration_to_webvtt, to_json


def build_demo() -> DemoDocument:
    """A small but complete demo: type a task into a to-do app, then save it.

    Commands live on the section's steps; the highlight + callout cues and the narration live on
    their own :class:`~walkthru.Tracks`, associated to a step **by anchor** (``stepId`` +
    ``localOffsetMs``) — the anchor is the single source of truth for that association.
    """
    save_button = Target(
        primary=Locator(strategy="role", value="button", name="Save"),
        fallbacks=[Locator(strategy="testid", value="save-btn")],
    )
    return DemoDocument(
        id="todo-quickstart",
        meta=Meta(
            title="Add and save a task",
            description="A three-beat tour of the to-do app.",
        ),
        sections=[
            Section(
                id="main",
                title="Adding your first task",
                steps=[
                    Beat(
                        id="title-card",
                        beat_kind="textCard",
                        timing=Timing(duration_ms=1500),
                        text="Welcome — let's add your first task.",
                    ),
                    CommandStep(
                        id="type-task",
                        command=Command(id="todo.add", params={"text": "Buy milk"}),
                        timing=Timing(duration_ms=1200),
                    ),
                    CommandStep(
                        id="save",
                        command=Command(id="todo.save"),
                        timing=Timing(duration_ms=800, hold_after_ms=400),
                    ),
                ],
            )
        ],
        tracks=Tracks(
            cues=[
                HighlightCue(
                    id="ring-save",
                    anchor=Anchor(step_id="save"),
                    target=save_button,
                    color="#ffcc00",
                ),
                CalloutCue(
                    id="tip-save",
                    anchor=Anchor(step_id="save", local_offset_ms=100),
                    target=save_button,
                    text="Click Save to persist your task.",
                    placement="top",
                ),
            ],
            narration=[
                NarrationSegment(
                    id="narr-type",
                    text="First, type the name of your task.",
                    anchor=NarrationAnchor(step_id="type-task", duration_ms=1200),
                ),
                NarrationSegment(
                    id="narr-save",
                    text="Then save it — your task is now stored.",
                    anchor=NarrationAnchor(step_id="save", duration_ms=800),
                ),
            ],
        ),
    )


async def app_executor(command: Command) -> dict:
    """Stand-in for the real app: 'runs' a command and returns a result.

    In a live run this is the seam to the application — e.g. acture's ``registry.dispatch`` or a
    Playwright ``page`` action. Here it just reports what it would do.
    """
    print(f"    ▶ executing {command.id}({command.params or {}})")
    return {"ok": True}


def make_logger() -> "callable":
    """A logging :data:`~walkthru.Observer` that narrates the lifecycle event stream.

    Every effect in walkthru is an observer; a recorder, an overlay renderer, and a narrator are
    all the same shape as this logger. It only *reads* events — the engine performs no I/O itself.
    """

    def log(event: Event) -> None:
        name = type(event).__name__
        if name == "StepEnter":
            print(f"  → step '{event.step.id}' ({event.step.kind})")
        elif name == "Narration":
            print(f"    🗣  {event.segment.text!r}")
        elif name == "CueBegin":
            print(f"    ✨ cue '{event.cue.id}' ({event.cue.type})")
        elif name == "BeatEvent":
            print(f"    ⏸  beat '{event.beat.beat_kind}': {event.beat.text!r}")

    return log


async def main() -> Outcome:
    document = build_demo()

    print("Playing the demo (generative mode):\n")
    outcome = await play(document, app_executor, observers=[make_logger()])
    print(f"\nOutcome: ok={outcome.ok}, steps_run={outcome.steps_run}\n")

    # The renderer hand-off. walkthru owns the *representation*; it hands a renderer the frozen
    # JSON artifact (the renderer owns the pixels) and a caption sidecar — both dependency-free.
    print("Frozen JSON projection (the renderer contract):")
    print(to_json(document))
    print("\nWebVTT captions (derived from the narration track):\n")
    print(narration_to_webvtt(document))

    return outcome


if __name__ == "__main__":
    asyncio.run(main())
