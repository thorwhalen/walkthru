"""walkthru — editable, re-renderable demo/tour artifacts from a command sequence.

walkthru owns the *representation* (the Demo Document) and a tiny pure playback/capture
engine, ``play(demoDoc, executor, observers)``. It never renders the final video — it hands a
validated artifact to a renderer (the ``reelee`` ecosystem, Remotion, moviepy/ffmpeg). Owning
representation, not pixels, is the load-bearing boundary of the design.

Two modes share one data model and one engine: *generative* (an author supplies the document;
walkthru plays it while recording) and *capture* (a human drives; walkthru records the video
and the underlying command stream into the same document).

See ``PLAN.md``, ``DECISIONS.md``, and the repository's enhancement issues for the design and
its running development journal. This package currently holds the Python side (schema SSOT +
core + render hand-off); the live capture/play engine ships separately as ``acture-walkthru``.

Quickstart::

    import asyncio
    from walkthru import DemoDocument, Section, CommandStep, Command, Timing, play

    doc = DemoDocument(
        id="demo",
        sections=[Section(id="s1", steps=[
            CommandStep(id="step-1", command=Command(id="app.open"), timing=Timing(duration_ms=500)),
        ])],
    )

    async def executor(command):
        print("run", command.id)
        return {"ok": True}

    asyncio.run(play(doc, executor))
"""

from walkthru.core import (  # noqa: F401
    Anchor,
    AssetRef,
    Beat,
    CalloutCue,
    Command,
    CommandInvocation,
    CommandStep,
    Cue,
    CursorCue,
    DemoDocument,
    Event,
    HighlightCue,
    HotspotCue,
    Locator,
    Meta,
    NarrationSegment,
    Observer,
    Outcome,
    Rect,
    ResolvedCamera,
    ResolvedCue,
    ResolvedNarration,
    ResolvedStep,
    Section,
    SpotlightCue,
    Step,
    Target,
    Timeline,
    Timing,
    Tracks,
    demo_document_json_schema,
    iter_events,
    iter_resolved_steps,
    play,
    record,
    resolve_timeline,
)

__version__ = "0.0.1"

__all__ = [
    "__version__",
    "play",
    "record",
    "iter_events",
    "resolve_timeline",
    "iter_resolved_steps",
    "Timeline",
    "ResolvedStep",
    "ResolvedCue",
    "ResolvedNarration",
    "ResolvedCamera",
    "demo_document_json_schema",
    "DemoDocument",
    "Meta",
    "Section",
    "Step",
    "CommandStep",
    "Beat",
    "Command",
    "Timing",
    "Anchor",
    "Target",
    "Locator",
    "Rect",
    "Tracks",
    "Cue",
    "HighlightCue",
    "SpotlightCue",
    "HotspotCue",
    "CalloutCue",
    "CursorCue",
    "NarrationSegment",
    "AssetRef",
    "Event",
    "Observer",
    "Outcome",
    "CommandInvocation",
]
