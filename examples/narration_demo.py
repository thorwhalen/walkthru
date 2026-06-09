"""Segmented narration → captions, end to end, with no TTS service (offline, runnable anywhere).

Authors a tiny Demo Document whose narration is split into per-beat segments, then:

1. ``realize_narration`` synthesizes + times each segment — here with an *offline* fake synthesizer
   that estimates duration from word count, so the example runs with no API key and no ffmpeg. Swap
   in ``walkthru.adapters.synth.MixingSynthesizer`` + ``mixing_duration_ms`` for real ElevenLabs audio.
2. ``pace_steps_to_narration`` holds each beat for at least as long as its line is spoken.
3. ``narration_to_webvtt`` / ``narration_to_srt`` emit captions straight off the resolved timeline.

Run::

    python examples/narration_demo.py
"""

import asyncio

from walkthru import (
    Command,
    CommandStep,
    DemoDocument,
    Meta,
    NarrationAnchor,
    NarrationSegment,
    Section,
    Timing,
    Tracks,
    pace_steps_to_narration,
    realize_narration,
    resolve_timeline,
)
from walkthru.adapters.export import narration_to_srt, narration_to_webvtt
from walkthru.core.schema import AssetRef

WORDS_PER_SECOND = 2.2  # roughly the ElevenLabs narration pace


class EstimatingSynth:
    """Offline stand-in for a real Synthesizer: no audio; duration estimated from word count."""

    async def say(self, text: str) -> AssetRef:
        return AssetRef(uri=f"estimated://{len(text.split())}-words", mime="audio/x-estimated")


def estimate_ms(asset: AssetRef) -> int:
    words = int(asset.uri.split("//")[1].split("-")[0])
    return int(words / WORDS_PER_SECOND * 1000)


def build_document() -> DemoDocument:
    steps = [
        CommandStep(id="open", command=Command(id="app.open"), timing=Timing(duration_ms=500)),
        CommandStep(id="focus", command=Command(id="app.focus"), timing=Timing(duration_ms=500)),
        CommandStep(id="reveal", command=Command(id="app.reveal"), timing=Timing(duration_ms=500)),
    ]
    narration = [
        NarrationSegment(
            id="n-open",
            text="Welcome — this is the dashboard you start from.",
            anchor=NarrationAnchor(step_id="open", duration_ms=0),
        ),
        NarrationSegment(
            id="n-focus",
            text="We focus the one panel that matters first.",
            anchor=NarrationAnchor(step_id="focus", duration_ms=0),
        ),
        NarrationSegment(
            id="n-reveal",
            text="And finally we reveal the result you came here for.",
            anchor=NarrationAnchor(step_id="reveal", duration_ms=0),
        ),
    ]
    return DemoDocument(
        id="narration-demo",
        meta=Meta(title="Segmented narration demo"),
        sections=[Section(id="s", steps=steps)],
        tracks=Tracks(narration=narration),
    )


def main() -> None:
    doc = build_document()
    realized = asyncio.run(realize_narration(doc, synth=EstimatingSynth(), measure_ms=estimate_ms))
    paced = pace_steps_to_narration(realized.document, policy="max")
    timeline = resolve_timeline(paced)
    print(f"total: {timeline.total_ms} ms over {len(timeline.steps)} steps\n")
    print("--- WebVTT ---")
    print(narration_to_webvtt(paced))
    print("--- SRT ---")
    print(narration_to_srt(paced))


if __name__ == "__main__":
    main()
