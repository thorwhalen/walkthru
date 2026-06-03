---
name: using-walkthru
description: >-
  How to USE walkthru as a library to build, play, capture, and export
  demo/tour artifacts. Use whenever someone wants to author a Demo Document,
  play a command sequence while recording, capture a human's actions into a
  reusable document, add visual cues / narration / camera moves, compute a
  timeline, or export to JSON, WebVTT captions, or video (via reelee). Also use
  for the TypeScript `acture-walkthru` package when validating a Demo Document
  with the generated Zod schema. Trigger even if the user just says "make a
  walkthrough/tour with walkthru", "play this demo and record it", "turn my
  clicks into a demo", "add a highlight + narration to step 3", or "export
  captions/video from my demo" — including when they don't name the exact API.
---

# Using walkthru

walkthru represents a demo/tour as an editable **Demo Document** and plays or
captures it. It deliberately does **not** render the final video — it produces a
validated artifact and hands it to a renderer. So a typical use falls into:
**author/capture a document → (optionally) play it with observers → resolve its
timeline → export** (JSON, captions, or video).

```bash
pip install walkthru                 # core (depends only on pydantic)
pip install "walkthru[playwright]"   # + browser ElementLocator/Recorder
pip install "walkthru[reelee]"       # + the Ken Burns mp4 RenderTarget
```

```ts
npm i acture-walkthru                // TS: the generated Zod schema + types
```

Everything public is imported from the top-level package:
`from walkthru import DemoDocument, Section, CommandStep, Command, Timing, play, record, resolve_timeline, ...`

## 1. Author a Demo Document

A document is sections of steps. A `CommandStep` runs a `Command`; timing is
**relative** (milliseconds). The smallest meaningful demo:

```python
from walkthru import DemoDocument, Section, CommandStep, Command, Timing

doc = DemoDocument(
    id="demo-minimal",
    sections=[
        Section(id="s1", steps=[
            CommandStep(id="step-1", command=Command(id="app.open"),
                        timing=Timing(duration_ms=500)),
            CommandStep(id="step-2", command=Command(id="app.click", params={"x": 1, "y": 2}),
                        timing=Timing(duration_ms=800, hold_after_ms=200)),
        ]),
    ],
)
```

`Command.id` is vendor-neutral (it mirrors acture's command identifiers).
`hold_after_ms` is dwell time before the next step starts. A `Beat` is a
non-command step (a pause, text card, or B-roll) — use it for narration-only or
title moments.

## 2. Play it (generative mode)

`play` is **async** and pure: it walks the document, calls your `executor` for
each command, and emits a lifecycle event stream to any `observers`. It records
nothing itself — recording, overlays, narration, and pacing are all observers.

```python
import asyncio
from walkthru import play
from walkthru.core.events import BeforeCommand, AfterCommand  # individual event classes live here

async def executor(command):           # runs one Command; sync or async both fine
    print("run", command.id, command.params)
    return {"ok": True}

async def logger(event):               # an observer: any callable taking one Event
    if isinstance(event, (BeforeCommand, AfterCommand)):
        print(type(event).__name__, event.command.id)

outcome = asyncio.run(play(doc, executor, observers=[logger]))
print(outcome.ok, outcome.steps_run, outcome.errors)
```

> **Where things import from.** The top-level `walkthru` package re-exports the
> engine (`play`, `record`, `resolve_timeline`, `iter_events`,
> `iter_resolved_steps`), the schema models you build documents from, and
> `Event`/`Observer`/`Outcome`. The *individual* lifecycle event classes
> (`BeforeCommand`, `AfterCommand`, `StepEnter`, `CueBegin`, `DemoStart`, …) live
> in `walkthru.core.events`, and a few companion schema types (`NarrationAnchor`,
> `CameraKeyframe`, `ScrollAnchor`, `TTS`, `WordTiming`) live in
> `walkthru.core.schema`. Import those from their modules.

Event order per run: `DemoStart → SectionEnter → StepEnter → BeforeCommand →
AfterCommand → StepExit → … → SectionExit → DemoEnd`, interleaved with
`CueBegin/CueEnd`, `Narration`, and `BeatEvent`. A real recording setup adds an
observer that calls a `Recorder` port on `DemoStart`/`DemoEnd` and a
`CueRenderer` on `CueBegin`/`CueEnd`.

## 3. Capture it (capture mode)

Same engine, opposite direction: feed a stream of executed commands and get the
**same** `DemoDocument` back. Useful for "record me doing this once, then replay
and re-render it."

```python
from walkthru import record, CommandInvocation, Command

async def captured():                  # yields commands as the human performs them
    yield CommandInvocation(command=Command(id="app.click", params={"x": 10, "y": 20}),
                            result={"ok": True}, duration_ms=800)

doc = asyncio.run(record(captured()))
```

In a real browser capture you'd get this stream from an `ActionRecorder` adapter
(e.g. over acture) and a `Recorder` for the video.

## 4. Annotate: cues, narration, camera

Annotations live in `doc.tracks` and attach to steps by **anchor**
(`{stepId, localOffsetMs}`) — they are *not* fields on the step. Targets are
resilient locators (a primary plus ordered fallbacks).

```python
from walkthru import (Tracks, HighlightCue, CalloutCue, Anchor,
                      Target, Locator, NarrationSegment)
from walkthru.core.schema import NarrationAnchor  # companion type (see note above)

target = Target(
    primary=Locator(strategy="role", value="button", name="Save"),
    fallbacks=[Locator(strategy="testid", value="save-btn")],
)
doc.tracks = Tracks(
    cues=[
        HighlightCue(id="c1", anchor=Anchor(step_id="step-2"), target=target, color="#ffcc00"),
        CalloutCue(id="c2", anchor=Anchor(step_id="step-2", local_offset_ms=100),
                   target=target, text="Click Save to persist.", placement="top"),
    ],
    narration=[
        NarrationSegment(id="n1", text="Now save your work.",
                         anchor=NarrationAnchor(step_id="step-2", duration_ms=1000)),
    ],
)
```

The five cue types are `HighlightCue`, `SpotlightCue`, `HotspotCue`,
`CalloutCue`, and `CursorCue`. Locator strategies: `role`, `testid`, `text`,
`label`, `css`, `xpath`. Narration `text` is the source of truth; `audio_ref`
and `tts` are regenerable and optional.

## 5. Resolve the timeline (relative → absolute)

The document stores only relative durations. To get absolute start/end times
(for a renderer, a scrubber, or captions), compose it:

```python
from walkthru import resolve_timeline

tl = resolve_timeline(doc)
print(tl.total_ms)
for rs in tl.steps:
    print(rs.step_id, rs.start_ms, rs.end_ms)
# tl.cues / tl.narration / tl.camera are likewise placed on absolute time
```

## 6. Export

Exporters live in `walkthru.adapters.export` (dependency-free) and
`walkthru.ecosystem.reelee` (needs the `reelee` extra):

```python
from walkthru.adapters.export import to_json, narration_to_webvtt

frozen = to_json(doc, indent=2)          # the canonical camelCase JSON projection
captions = narration_to_webvtt(doc)      # WebVTT captions from the narration track

# Video (requires: pip install "walkthru[reelee]")
import asyncio
from walkthru.ecosystem.reelee import render_demo_video
mp4_path = asyncio.run(render_demo_video(doc))
```

`to_json` is the primary hand-off contract: any renderer (or the TS side) consumes
that frozen JSON. To plug in your own renderer, implement the `RenderTarget` port
— see the **`walkthru-adapter`** skill.

## 7. TypeScript: validate a Demo Document

The npm package ships a Zod schema generated from the same SSOT, so a document
produced in Python validates in TS with no loss:

```ts
import { demoDocumentSchema, type DemoDocument } from "acture-walkthru";

const doc: DemoDocument = demoDocumentSchema.parse(JSON.parse(jsonString));
// Unknown cue types / wrong field types are rejected (the unions are closed).
```

## Gotchas

- **`play` and `record` are async** — wrap in `asyncio.run(...)` (or `await`).
  Your `executor`/observers may be sync or async; the engine handles both.
- **Time is relative and in milliseconds.** Never put absolute timestamps in a
  document; derive absolute time with `resolve_timeline`.
- **The wire format is camelCase** (`durationMs`, `holdAfterMs`, `stepId`).
  Python attributes are snake_case; dump with `model_dump_json(by_alias=True)` or
  use `to_json`.
- **Annotations attach by anchor**, not by editing the step. Add/move a cue by
  changing its `anchor`, and its `target` is what locates the element at render
  time.
- The core needs no browser or renderer. Install `[playwright]` / `[reelee]`
  extras only when you actually drive a real backend.
