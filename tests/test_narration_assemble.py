"""Tests for narration_slots / assemble_narration_audio — pure slotting + injected assembler."""

from __future__ import annotations

from pathlib import Path

import pytest

from walkthru import (
    Command,
    CommandStep,
    DemoDocument,
    NarrationAnchor,
    NarrationSegment,
    Section,
    Timing,
    Tracks,
    assemble_narration_audio,
    narration_slots,
    resolve_timeline,
)
from walkthru.core.schema import AssetRef


def _doc() -> DemoDocument:
    return DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=1000)),
                    CommandStep(id="step-2", command=Command(id="b"), timing=Timing(duration_ms=1000)),
                    CommandStep(id="step-3", command=Command(id="c"), timing=Timing(duration_ms=1000)),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n1",
                    text="a",
                    anchor=NarrationAnchor(step_id="step-1", duration_ms=800),
                    audio_ref=AssetRef(uri="/clips/a.wav", mime="audio/wav"),
                ),
                NarrationSegment(
                    id="n2",
                    text="b",
                    anchor=NarrationAnchor(step_id="step-2", local_offset_ms=200, duration_ms=500),
                    audio_ref=AssetRef(uri="/clips/b.wav", mime="audio/wav"),
                ),
            ]
        ),
    )


def test_slots_place_clips_with_silence_gaps_and_tail():
    slots = narration_slots(resolve_timeline(_doc()))  # total 3000ms
    assert slots == [
        (Path("/clips/a.wav"), 0.8),  # n1 [0, 800]
        (None, 0.4),  # gap 800 -> 1200
        (Path("/clips/b.wav"), 0.5),  # n2 [1200, 1700]
        (None, 1.3),  # tail 1700 -> 3000
    ]


def test_slots_overlap_raises():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=2000))],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n1", text="a",
                    anchor=NarrationAnchor(step_id="step-1", duration_ms=600),
                    audio_ref=AssetRef(uri="/a.wav"),
                ),
                NarrationSegment(
                    id="n2", text="b",
                    anchor=NarrationAnchor(step_id="step-1", local_offset_ms=300, duration_ms=600),
                    audio_ref=AssetRef(uri="/b.wav"),
                ),
            ]
        ),
    )
    with pytest.raises(ValueError, match="overlap"):
        narration_slots(resolve_timeline(doc))


def test_assemble_hands_slots_to_injected_assembler():
    captured: dict = {}

    def fake_assembler(segments, *, output, **_):
        captured["segments"] = list(segments)
        captured["output"] = output
        return Path(output)

    out = assemble_narration_audio(resolve_timeline(_doc()), "/tmp/out.wav", assembler=fake_assembler)
    assert out == Path("/tmp/out.wav")
    assert captured["segments"][0] == (Path("/clips/a.wav"), 0.8)
    assert captured["output"] == Path("/tmp/out.wav")


def test_assemble_returns_none_when_track_is_all_silence():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=1000))],
            )
        ],
    )  # no narration at all
    called: list[int] = []
    out = assemble_narration_audio(
        resolve_timeline(doc), "/tmp/out.wav", assembler=lambda *a, **k: called.append(1)
    )
    assert out is None
    assert not called  # assembler never invoked when there is nothing to mux


def test_slots_lead_with_silence_when_first_segment_starts_late():
    # Boundary: the first (here only) narration segment starts at a positive offset -> lead-in silence.
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=1000)),
                    CommandStep(id="step-2", command=Command(id="b"), timing=Timing(duration_ms=1000)),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n1", text="late",
                    anchor=NarrationAnchor(step_id="step-1", local_offset_ms=500, duration_ms=400),
                    audio_ref=AssetRef(uri="/clips/late.wav"),
                )
            ]
        ),
    )
    slots = narration_slots(resolve_timeline(doc))  # total 2000ms
    assert slots == [
        (None, 0.5),  # lead-in silence 0 -> 500
        (Path("/clips/late.wav"), 0.4),  # n1 [500, 900]
        (None, 1.1),  # tail 900 -> 2000
    ]
