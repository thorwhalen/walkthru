# walkthru

Turn a sequence of application **commands** into an **editable, re-renderable demo/tour
artifact** — and play that sequence while observers record video, draw visual cues, and
narrate.

`walkthru` owns the **representation** (the *Demo Document*) and the **playback/capture
engine**. It does **not** render the final video — it hands a validated artifact off to a
renderer (the `reelee` ecosystem, Remotion, moviepy/ffmpeg, …). *Owning representation, not
pixels, is the load-bearing boundary of the whole design.*

## Two modes, one data model, one engine

- **Generative** — an author supplies a Demo Document (commands + annotations); `walkthru`
  plays it while recording, with optional cues (highlight, spotlight, hotspot, callout,
  synthetic cursor), pauses, and narration.
- **Capture** — a human operates the app manually; `walkthru` records the video **and** the
  underlying command stream **and** annotations, producing the *same* Demo Document.

The only difference between the modes is *who fills in the document*.

## The core

```
play(demoDoc, executor, observers) -> Outcome
```

A pure higher-order function that walks the document and emits lifecycle events
(`onStepEnter` → `beforeCommand` → `afterCommand` → `onStepExit`, `onCueBegin/End`,
`onNarration`, …). It never records, renders, or speaks — every effect is an injected
observer or port.

## Quickstart

```bash
pip install walkthru
```

```python
import asyncio
from walkthru import DemoDocument, Section, CommandStep, Command, Timing, play

doc = DemoDocument(
    id="demo",
    sections=[Section(id="s1", steps=[
        CommandStep(id="step-1", command=Command(id="app.open"), timing=Timing(duration_ms=500)),
        CommandStep(id="step-2", command=Command(id="app.save"), timing=Timing(duration_ms=800)),
    ])],
)

async def executor(command):           # your app's command bus (acture, Playwright, …)
    print("run", command.id)
    return {"ok": True}

asyncio.run(play(doc, executor))       # → runs step-1, step-2; returns an Outcome
```

Three runnable scripts in [`examples/`](./examples) go further — a **generative** demo (commands +
cues + narration, with JSON + WebVTT hand-off), a **capture** demo (record a human's actions into the
same document and replay it), and a **narration** demo (segment → time → caption). All are pure-core,
no optional deps:

```bash
python examples/generative_demo.py
python examples/capture_demo.py
python examples/narration_demo.py
```

## Narration & captions

Narration is a track of editable **text** anchored to steps (the Descript model: text is the source
of truth; audio and timing are regenerable). Turning authored text into timed, voiced narration with
captions is a three-step, fully composable pipeline:

```python
from walkthru import realize_narration, pace_steps_to_narration, resolve_timeline
from walkthru.adapters.export import narration_to_webvtt, narration_to_srt
from walkthru.adapters.synth import MixingSynthesizer, mixing_duration_ms

# 1. Synthesize each segment and time it from its own audio (anchor.duration_ms ← measured clip).
synth = MixingSynthesizer(voice_query="narrative_story", out_dir="tts")   # [synth] extra → ElevenLabs
realized = await realize_narration(doc, synth=synth, measure_ms=mixing_duration_ms)

# 2. (optional) Hold each beat at least as long as its line is spoken — narration-led pacing.
paced = pace_steps_to_narration(realized.document, policy="max")

# 3. Captions fall straight out of the resolved timeline — WebVTT (web-native) and SRT (universal).
open("demo.vtt", "w").write(narration_to_webvtt(paced))
open("demo.srt", "w").write(narration_to_srt(paced))
```

Because each segment is synthesized and measured independently, the beat boundaries fall out of
`resolve_timeline` with **no alignment math**. Synthesis is the `Synthesizer` port and the audio
assembler is an injected seam, so the whole flow is testable with fakes and pulls in no media stack;
`MixingSynthesizer` (the `[synth]` extra) is the hosted-voice tier. See `examples/narration_demo.py`
for an offline run (no API key) and `DECISIONS.md` §D8/§D12.

## Ecosystem-biased, ecosystem-independent

The core and ports depend on **nothing** from our ecosystem. Integration with
[`acture`](https://github.com/thorwhalen/acture) (the command layer),
[`reelee`](https://github.com/thorwhalen/reelee) (the renderer), and `zodal` ships as
**optional adapters**. You can `pip install walkthru` / `npm i acture-walkthru` and use the
core with your own adapters.

## Packages

| Package | Registry | Role |
|---|---|---|
| `walkthru` | PyPI | Python core + schema SSOT + render hand-off |
| `acture-walkthru` | npm | TS core + the live capture/play engine over `acture` |

## Status

The **Python side is implemented**: the Demo Document schema (the SSOT), the pure play/capture
engine, dependency-free JSON + WebVTT + SRT export, segmented narration (synthesize → time → pace →
assemble), and the first adapters (Playwright locator/recorder, the `mixing`/ElevenLabs voice
synthesizer, and the [`reelee`](https://github.com/thorwhalen/reelee) Ken Burns render target). The TypeScript
package currently ships the **schema seam** — a Zod validator codegened from the Pydantic SSOT — and
its live capture/play engine over `acture` lands next.

See [`PLAN.md`](./PLAN.md) for the implementation plan, [`DECISIONS.md`](./DECISIONS.md) for design
decisions and deviations from the brief, and the repo's **enhancement issues** for the running
development journal. Source documents live in [`misc/docs/`](./misc/docs/).

## License

MIT — see [`LICENSE`](./LICENSE).
