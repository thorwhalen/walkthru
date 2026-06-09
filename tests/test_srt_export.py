"""Tests for narration_to_srt — SRT captions off the resolved timeline, agreeing with WebVTT."""

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
)
from walkthru.adapters.export import narration_to_srt, narration_to_webvtt


def _doc() -> DemoDocument:
    return DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=2000)),
                    CommandStep(id="step-2", command=Command(id="b"), timing=Timing(duration_ms=2000)),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(id="n1", text="First line.", anchor=NarrationAnchor(step_id="step-1", duration_ms=1500)),
                NarrationSegment(id="n2", text="Second line.", anchor=NarrationAnchor(step_id="step-2", duration_ms=1800)),
            ]
        ),
    )


def test_srt_format_is_exact():
    expected = (
        "1\n00:00:00,000 --> 00:00:01,500\nFirst line.\n\n"
        "2\n00:00:02,000 --> 00:00:03,800\nSecond line.\n"
    )
    assert narration_to_srt(_doc()) == expected


def test_srt_empty_when_no_narration():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=1000))],
            )
        ],
    )
    assert narration_to_srt(doc) == ""


def test_srt_and_webvtt_agree_on_timing_differ_on_separator():
    srt, vtt = narration_to_srt(_doc()), narration_to_webvtt(_doc())
    assert "00:00:02,000" in srt  # SRT: comma
    assert "00:00:02.000" in vtt  # WebVTT: dot
