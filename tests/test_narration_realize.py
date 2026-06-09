"""Tests for realize_narration — the synthesize-and-time loop, with fakes (no TTS, no ffmpeg)."""

from __future__ import annotations

import asyncio

from walkthru import (
    Command,
    CommandStep,
    DemoDocument,
    NarrationAnchor,
    NarrationSegment,
    RealizedNarration,
    Section,
    Timing,
    Tracks,
    realize_narration,
    resolve_timeline,
)
from walkthru.core.schema import AssetRef


class LenSynth:
    """Fake Synthesizer whose clip uri encodes the text length (so a probe can derive duration)."""

    def __init__(self) -> None:
        self.said: list[str] = []

    async def say(self, text: str) -> AssetRef:
        self.said.append(text)
        return AssetRef(uri=f"mem://{len(text)}.wav", mime="audio/wav")


def _measure_ms(asset: AssetRef) -> int:
    # 50ms per encoded character — deterministic, derived from the asset alone.
    n = int(asset.uri.split("//")[1].split(".")[0])
    return n * 50


def _doc() -> DemoDocument:
    return DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=100)),
                    CommandStep(id="step-2", command=Command(id="b"), timing=Timing(duration_ms=100)),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(id="n1", text="hi", anchor=NarrationAnchor(step_id="step-1", duration_ms=0)),
                NarrationSegment(id="n2", text="hello!", anchor=NarrationAnchor(step_id="step-2", duration_ms=0)),
            ]
        ),
    )


def test_realize_sets_durations_and_audio():
    synth = LenSynth()
    result = asyncio.run(realize_narration(_doc(), synth=synth, measure_ms=_measure_ms))
    assert isinstance(result, RealizedNarration)
    segs = {s.id: s for s in result.document.tracks.narration}
    assert segs["n1"].anchor.duration_ms == len("hi") * 50  # 100
    assert segs["n2"].anchor.duration_ms == len("hello!") * 50  # 300
    assert segs["n1"].audio_ref.uri == "mem://2.wav"
    assert result.audio_by_segment["n2"].uri == "mem://6.wav"
    assert synth.said == ["hi", "hello!"]


def test_realize_does_not_mutate_input():
    doc = _doc()
    asyncio.run(realize_narration(doc, synth=LenSynth(), measure_ms=_measure_ms))
    assert doc.tracks.narration[0].anchor.duration_ms == 0
    assert doc.tracks.narration[0].audio_ref is None


def test_realize_invokes_on_segment_callback_in_order():
    seen: list[tuple[str, str, int]] = []
    asyncio.run(
        realize_narration(
            _doc(),
            synth=LenSynth(),
            measure_ms=_measure_ms,
            on_segment=lambda seg, asset, ms: seen.append((seg.id, asset.uri, ms)),
        )
    )
    assert [s[0] for s in seen] == ["n1", "n2"]
    assert seen[0] == ("n1", "mem://2.wav", 100)


def test_realized_timeline_lands_segments_at_step_starts():
    result = asyncio.run(realize_narration(_doc(), synth=LenSynth(), measure_ms=_measure_ms))
    by_id = {n.segment_id: n for n in resolve_timeline(result.document).narration}
    # step-1 starts at 0 → n1 spans its 100ms; step-2 starts at 100 → n2 spans 300ms
    assert (by_id["n1"].start_ms, by_id["n1"].end_ms) == (0, 100)
    assert (by_id["n2"].start_ms, by_id["n2"].end_ms) == (100, 400)


def test_realize_handles_empty_narration_track():
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[CommandStep(id="step-1", command=Command(id="a"), timing=Timing(duration_ms=100))],
            )
        ],
    )
    result = asyncio.run(realize_narration(doc, synth=LenSynth(), measure_ms=_measure_ms))
    assert result.audio_by_segment == {}
    assert list(result.document.tracks.narration) == []
