"""Timeline tests: relative durations compose into the right absolute times."""

from __future__ import annotations

import pytest

from walkthru.core.schema import (
    Anchor,
    Command,
    CommandStep,
    DemoDocument,
    HighlightCue,
    Section,
    Timing,
    Tracks,
)
from walkthru.core.timeline import resolve_timeline

from tests.builders import make_full_demo, make_minimal_demo


def test_minimal_step_starts_compose_with_hold():
    # step-1: dur 500, no hold -> [0, 500); step-2 starts at 500, dur 800 -> [500, 1300), hold 200.
    tl = resolve_timeline(make_minimal_demo())
    starts = {s.step_id: (s.start_ms, s.end_ms) for s in tl.steps}
    assert starts == {"step-1": (0, 500), "step-2": (500, 1300)}
    # total includes the trailing hold of the last step.
    assert tl.total_ms == 1500


def test_full_demo_absolute_times():
    # step-1 (dur 1000, hold 200) -> [0,1000); beat-1 (dur 400) starts at 1200 -> [1200,1600);
    # step-2 (dur 600) starts at 1600 -> [1600,2200).
    tl = resolve_timeline(make_full_demo())
    starts = {s.step_id: (s.start_ms, s.end_ms) for s in tl.steps}
    assert starts == {
        "step-1": (0, 1000),
        "beat-1": (1200, 1600),
        "step-2": (1600, 2200),
    }
    assert tl.total_ms == 2200


def test_full_demo_cue_times_anchor_to_step_start_plus_offset():
    tl = resolve_timeline(make_full_demo())
    cues = {c.cue_id: (c.start_ms, c.end_ms) for c in tl.cues}
    # all anchor to step-2 (start 1600); offsets 0/50/100/150/200; no duration -> end at step end 2200.
    assert cues["cue-highlight"] == (1600, 2200)
    assert cues["cue-spotlight"] == (1650, 2200)
    assert cues["cue-cursor"] == (1800, 2200)


def test_full_demo_narration_and_camera_times():
    tl = resolve_timeline(make_full_demo())
    (narr,) = tl.narration
    assert (narr.start_ms, narr.end_ms) == (
        0,
        1000,
    )  # step-1 start + offset 0, duration 1000
    (cam,) = tl.camera
    assert cam.at_ms == 1600  # step-2 start + offset 0


def test_cue_with_explicit_duration_ends_at_offset_plus_duration():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(
                        id="a", command=Command(id="x"), timing=Timing(duration_ms=1000)
                    ),
                ],
            )
        ],
        tracks=Tracks(
            cues=[
                HighlightCue(
                    id="c",
                    anchor=Anchor(step_id="a", local_offset_ms=100),
                    duration_ms=200,
                ),
            ]
        ),
    )
    (cue,) = resolve_timeline(doc).cues
    assert (cue.start_ms, cue.end_ms) == (100, 300)


def test_dangling_anchor_fails_fast():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(
                        id="a", command=Command(id="x"), timing=Timing(duration_ms=100)
                    ),
                ],
            )
        ],
        tracks=Tracks(
            cues=[
                HighlightCue(id="c", anchor=Anchor(step_id="does-not-exist")),
            ]
        ),
    )
    with pytest.raises(ValueError, match="unknown step 'does-not-exist'"):
        resolve_timeline(doc)


def test_lookup_by_step_id():
    tl = resolve_timeline(make_minimal_demo())
    assert tl.step("step-2").start_ms == 500
    with pytest.raises(KeyError):
        tl.step("nope")
