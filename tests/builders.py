"""Demo Document builders shared across tests."""

from __future__ import annotations

from walkthru.core.schema import (
    Anchor,
    CalloutCue,
    Command,
    CommandStep,
    DemoDocument,
    HighlightCue,
    Locator,
    Meta,
    NarrationAnchor,
    NarrationSegment,
    Section,
    Target,
    Timing,
    Tracks,
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
