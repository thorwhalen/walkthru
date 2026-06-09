"""Tests for pace_steps_to_narration — the optional, pure narration-led step pacing policy."""

from __future__ import annotations

from walkthru import (
    Command,
    CommandStep,
    DemoDocument,
    NarrationAnchor,
    NarrationSegment,
    Section,
    Timing,
    Tracks,
    pace_steps_to_narration,
)


def _doc(step1_dur: int = 500) -> DemoDocument:
    return DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=step1_dur)),
                    CommandStep(id="step-2", command=Command(id="b"), timing=Timing(duration_ms=500)),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(id="n1", text="x", anchor=NarrationAnchor(step_id="step-1", duration_ms=1200)),
            ]
        ),
    )


def _durations(doc: DemoDocument) -> dict[str, int]:
    return {s.id: s.timing.duration_ms for s in doc.sections[0].steps}


def test_keep_is_noop_identity():
    doc = _doc()
    assert pace_steps_to_narration(doc, policy="keep") is doc


def test_max_grows_short_step_leaves_unnarrated_step():
    durs = _durations(pace_steps_to_narration(_doc(step1_dur=500), policy="max"))
    assert durs["step-1"] == 1200  # grew to narration extent
    assert durs["step-2"] == 500  # no narration → unchanged


def test_max_keeps_longer_step():
    durs = _durations(pace_steps_to_narration(_doc(step1_dur=2000), policy="max"))
    assert durs["step-1"] == 2000  # already longer than narration → unchanged


def test_narration_policy_sets_exact_extent_and_leaves_unnarrated_step():
    durs = _durations(pace_steps_to_narration(_doc(step1_dur=2000), policy="narration"))
    assert durs["step-1"] == 1200  # set to the narration extent exactly
    assert durs["step-2"] == 500  # no narration → unchanged even under the "narration" policy


def test_extent_is_max_over_multiple_segments_on_same_step():
    # Two segments on step-1; the max-extent one is NOT last, to pin down max() (not "last segment").
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=100))],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n-long", text="x",
                    anchor=NarrationAnchor(step_id="step-1", local_offset_ms=200, duration_ms=300),
                ),  # extent 500
                NarrationSegment(
                    id="n-short", text="y",
                    anchor=NarrationAnchor(step_id="step-1", local_offset_ms=0, duration_ms=100),
                ),  # extent 100
            ]
        ),
    )
    out = pace_steps_to_narration(doc, policy="max")
    assert out.sections[0].steps[0].timing.duration_ms == 500


def test_extent_includes_local_offset():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=100))],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n1",
                    text="x",
                    anchor=NarrationAnchor(step_id="step-1", local_offset_ms=300, duration_ms=400),
                )
            ]
        ),
    )
    out = pace_steps_to_narration(doc, policy="max")
    assert out.sections[0].steps[0].timing.duration_ms == 700  # 300 + 400


def test_does_not_mutate_input():
    doc = _doc(step1_dur=500)
    pace_steps_to_narration(doc, policy="max")
    assert doc.sections[0].steps[0].timing.duration_ms == 500
