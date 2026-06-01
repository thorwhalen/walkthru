"""Demo Document builders shared across tests."""

from __future__ import annotations

from walkthru.core.schema import (
    Anchor,
    AssetRef,
    Beat,
    CalloutCue,
    CameraKeyframe,
    Command,
    CommandStep,
    CursorCue,
    DemoDocument,
    HighlightCue,
    HotspotCue,
    Locator,
    Meta,
    NarrationAnchor,
    NarrationSegment,
    Rect,
    ScrollAnchor,
    Section,
    SpotlightCue,
    Target,
    Timing,
    Tracks,
    TTS,
    WordTiming,
)


def make_minimal_demo() -> DemoDocument:
    """The smallest meaningful demo: two command steps in one section, no annotations."""
    return DemoDocument(
        id="demo-minimal",
        sections=[
            Section(
                id="s1",
                steps=[
                    CommandStep(
                        id="step-1",
                        command=Command(id="app.open"),
                        timing=Timing(duration_ms=500),
                    ),
                    CommandStep(
                        id="step-2",
                        command=Command(id="app.click", params={"x": 1, "y": 2}),
                        timing=Timing(duration_ms=800, hold_after_ms=200),
                    ),
                ],
            )
        ],
    )


def make_rich_demo() -> DemoDocument:
    """A demo exercising every track: a highlight cue, a callout cue, and narration."""
    target = Target(
        primary=Locator(strategy="role", value="button", name="Save"),
        fallbacks=[Locator(strategy="testid", value="save-btn")],
    )
    return DemoDocument(
        id="demo-rich",
        meta=Meta(title="Saving your work", description="A two-step save flow."),
        sections=[
            Section(
                id="intro",
                title="Intro",
                steps=[
                    CommandStep(
                        id="step-1",
                        command=Command(id="doc.edit", params={"text": "hello"}),
                        timing=Timing(duration_ms=1000),
                    ),
                    CommandStep(
                        id="step-2",
                        command=Command(id="doc.save"),
                        timing=Timing(duration_ms=600),
                    ),
                ],
            )
        ],
        tracks=Tracks(
            cues=[
                HighlightCue(
                    id="c1",
                    anchor=Anchor(step_id="step-2"),
                    target=target,
                    color="#ffcc00",
                ),
                CalloutCue(
                    id="c2",
                    anchor=Anchor(step_id="step-2", local_offset_ms=100),
                    target=target,
                    text="Click Save to persist your changes.",
                    placement="top",
                ),
            ],
            narration=[
                NarrationSegment(
                    id="n1",
                    text="First, let's type some text.",
                    anchor=NarrationAnchor(step_id="step-1", duration_ms=1000),
                ),
            ],
        ),
    )


def make_full_demo() -> DemoDocument:
    """The broadest fixture: every Step kind, all five cue types, and every track.

    Exists to exercise the schema's discriminated unions (``Step.kind``, ``Cue.type``) and
    optional sub-objects (``Target.bbox``/``scrollAnchor``, ``NarrationSegment.tts``/
    ``wordTimings``, ``CameraKeyframe``) end to end — the surface the Python↔TS round-trip test
    relies on to prove the codegened Zod is faithful to the Pydantic SSOT.
    """
    target = Target(
        primary=Locator(strategy="role", value="button", name="Save"),
        fallbacks=[
            Locator(strategy="testid", value="save-btn"),
            Locator(strategy="css", value="button.save"),
        ],
        bbox=Rect(x=10, y=20, width=120, height=40),
        scroll_anchor=ScrollAnchor(
            locator=Locator(strategy="testid", value="scroll-pane"),
            fraction=0.25,
        ),
    )
    return DemoDocument(
        id="demo-full",
        meta=Meta(title="The full tour", description="Exercises every schema branch."),
        sections=[
            Section(
                id="intro",
                title="Intro",
                steps=[
                    CommandStep(
                        id="step-1",
                        command=Command(id="doc.edit", params={"text": "hello"}),
                        timing=Timing(duration_ms=1000, hold_after_ms=200),
                        poster=AssetRef(uri="assets/step-1.png", mime="image/png"),
                    ),
                    Beat(
                        id="beat-1",
                        beat_kind="textCard",
                        timing=Timing(duration_ms=400),
                        text="Now let's save.",
                        poster=AssetRef(uri="assets/beat-1.png", mime="image/png"),
                    ),
                    CommandStep(
                        id="step-2",
                        command=Command(id="doc.save"),
                        timing=Timing(duration_ms=600),
                    ),
                ],
            )
        ],
        tracks=Tracks(
            cues=[
                HighlightCue(
                    id="cue-highlight",
                    anchor=Anchor(step_id="step-2"),
                    target=target,
                    color="#ffcc00",
                    thickness=2,
                    padding=4,
                    shape="rect",
                ),
                SpotlightCue(
                    id="cue-spotlight",
                    anchor=Anchor(step_id="step-2", local_offset_ms=50),
                    target=target,
                    opacity=0.6,
                    color="#000000",
                    feather=8,
                ),
                HotspotCue(
                    id="cue-hotspot",
                    anchor=Anchor(step_id="step-2", local_offset_ms=100),
                    target=target,
                    pulse="double",
                    size=24,
                ),
                CalloutCue(
                    id="cue-callout",
                    anchor=Anchor(step_id="step-2", local_offset_ms=150),
                    target=target,
                    text="Click Save to persist your changes.",
                    placement="top",
                    arrow=True,
                ),
                CursorCue(
                    id="cue-cursor",
                    anchor=Anchor(step_id="step-2", local_offset_ms=200),
                    target=target,
                    from_target=Target(
                        primary=Locator(strategy="testid", value="editor"),
                    ),
                    click=True,
                    easing="ease-in-out",
                ),
            ],
            narration=[
                NarrationSegment(
                    id="narr-1",
                    text="First, let's type some text.",
                    anchor=NarrationAnchor(step_id="step-1", duration_ms=1000),
                    audio_ref=AssetRef(uri="assets/narr-1.wav", mime="audio/wav"),
                    tts=TTS(engine="piper", voice="en_US-amy", rate=1.0),
                    word_timings=[
                        WordTiming(word="First", t_ms=0),
                        WordTiming(word="let's", t_ms=300),
                    ],
                ),
            ],
            camera=[
                CameraKeyframe(
                    id="cam-1",
                    anchor=Anchor(step_id="step-2"),
                    focus=Rect(x=0, y=0, width=200, height=100),
                    zoom=1.5,
                    easing="ease-out",
                    hold_ms=300,
                ),
            ],
        ),
    )
