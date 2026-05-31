# Tooling & Capability Survey: A “Play-Commands-and-Record-a-Demo” System

**Author: Thor Whalen**

## TL;DR

- For **web-app demos**, a single tool — **Playwright** (≥ v1.59) — collapses four of the five capability slots (command player, video capture, visual cues via its new `page.screencast` Overlay API, and human-action recording via codegen), so the architecture reduces to “wrap Playwright + bolt on narration.” Wrap each Playwright capability behind your own dependency-injected port; do not let Playwright types leak into the core.
- For **desktop-app demos**, no single tool collapses the slots: you pair **OBS Studio** (driven via `obsws-python`) or **ffmpeg** for pixel capture with **platform accessibility APIs** (pywinauto/UIA on Windows, AT-SPI on Linux, AX on macOS) for element bounds — and Level-2 visual cues become materially harder because you must paint an OS-level click-through overlay window rather than inject DOM.
- The clean architecture is a small core that owns a **command stream + annotation timeline** as plain serializable data (JSON, round-tripped to WebVTT/SRT for narration and to OpenTimelineIO/EDL for the editor hand-off), with every behavior — capture, recording, cues, STT, TTS, render — behind an injected interface (`Recorder`, `ActionRecorder`, `CueRenderer`, `Transcriber`, `Synthesizer`, `RenderTarget`). The hand-off to a renderer such as **WebReel/Remotion** is just “emit the artifact,” never “embed the renderer.”

-----

## Key Findings

1. **Two capture philosophies, two winners by use case.** *Pixel video* (Playwright built-in, ffmpeg, OBS) is universal, editable by any video tool, and faithful to exactly what rendered — but heavy and not structurally editable. *DOM replay* (rrweb) is tiny, structurally editable (it is JSON), and re-renderable after edits, but web-only and fragile on canvas/WebGL/cross-origin iframes. **For DEMOS, pixel video wins** because the output must be a shareable video file and must survive non-DOM content; rrweb’s structural editability is a strong *secondary* artifact for the “capture mode” command stream, not the primary deliverable.
1. **Playwright is the unifying tool for web** and, as of v1.59 (Nov 2025), explicitly ships demo-grade primitives: `page.screencast.start/stop` (WebM, VP8/VP9), `showActions()` (highlights each interacted element), `showChapter()` (blurred-backdrop title cards), `showOverlay(html)` (arbitrary HTML, `pointer-events: none`),  and an `onFrame` JPEG stream. Its historical weakness is documented in Playwright GitHub Issue #31424 — for Chromium-based browsers the “target bitrate = 1Mbit/s is hardcoded… limited to one thread and target cpu usage is 50%”  — and the Playwright Videos docs note “The video size defaults to the viewport size scaled down to fit 800x800.”  That ceiling is the main reason demo-quality output may still need an external capturer (OBS/ffmpeg) for 1080p/60.
1. **Visual-cue libraries split into “cue renderers” vs “tour frameworks.”** **driver.js** (MIT, ~5 KB) is the cleanest reusable spotlight/highlight primitive; **Shepherd.js** (now MIT, ~25 KB, built on Floating UI) is the best customizable choice when cues must look native. **intro.js** is AGPL/commercial — a licensing trap for proprietary use. Smooth “cinematic” motion (synthetic cursor, zoom-to-element, click ripples) is **not proprietary magic**: it is CSS transforms + FLIP, deliverable with **Motion** (formerly Framer Motion, MIT) or hand-rolled `transform` animation.
1. **Narration is a solved two-stage pipeline.** STT: **WhisperX** (BSD-4-Clause, per the m-bain/whisperX package metadata) is the right default for *timed* text — its README advertises “Batched inference for 70x realtime transcription using whisper large-v2”  with forced-alignment to word-level timestamps; **faster-whisper** (MIT) is the fast engine underneath. TTS: **Piper** (MIT, CPU, edge) and **Kokoro** (Apache-2.0) for permissive commercial use; **XTTS-v2** (Coqui Public Model License — non-commercial) for cloning quality; **ElevenLabs/OpenAI/Azure** hosted for top quality. Timed text round-trips as **WebVTT/SRT**; the Descript model (“edit transcript → edit media”) is reproducible because each word is aligned to a media offset.
1. **The editor hand-off should target a real interchange format.** **OpenTimelineIO** (Apache-2.0, Python-native, adapters for EDL/FCP7-XML/FCPX-XML) is the realistic carrier for an editable demo timeline; **rrweb event JSON** is the carrier for the *command/interaction* layer. The downstream renderer pairs naturally with **Remotion** (React; free for individuals and companies up to three people,  paid Company License at 4+ people), **Revideo** (MIT, Motion-Canvas fork, render API), **Motion Canvas** (MIT), **moviepy/ffmpeg** (Python), or **WebReel** (Vercel Labs, Apache-2.0) — the last being the closest existing analog to the system being designed.

-----

## Details

### A. Capture (video / replay)

#### A.1 Pixel video vs DOM replay — the core trade-off

|Dimension                      |Pixel video (Playwright/ffmpeg/OBS)                            |DOM replay (rrweb)                                                                           |
|-------------------------------|---------------------------------------------------------------|---------------------------------------------------------------------------------------------|
|Fidelity                       |Exactly what rendered; survives canvas/WebGL/video/cross-origin|Reconstructs DOM; **breaks on canvas/WebGL/nested iframes/shadow DOM** unless plugins enabled|
|File size                      |Large (MB–GB)                                                  |Tiny (JSON deltas; full snapshot + incremental diffs)                                        |
|Editability                    |Frame-level only (need NLE)                                    |Structural — it is JSON; mutate events                                                       |
|Re-render after annotation edit|Re-run capture or re-composite                                 |Replay engine re-renders from events                                                         |
|Scope                          |Universal (web + desktop)                                      |Web only                                                                                     |
|“Lies over time” risk          |None (frozen pixels)                                           |Yes — replaying later can show *today’s* data, advancing clocks, changed API responses       |

rrweb works by taking a full DOM snapshot as a keyframe, then emitting incremental snapshots (mutations, mouse moves, scrolls, input) as timestamped JSON deltas — “similar to how video files work, but the snapshots don’t contain any pixel data, just DOM information.”  Browserbase publicly **migrated away from rrweb to CDP-screencast pixel video**; their engineering blog (“This week we fixed the worst part of Browserbase”) states: “The problem is that the web is not a controlled environment… Nested iframes break this model almost immediately… Canvas, WebGL, video elements, shadow DOM - anything that isn’t ‘normal’ HTML becomes either flaky or invisible… the easiest and most reliable way to show what happened in a browser is to just record what was on the screen.”  That is a strong signal: **for a polished demo deliverable, capture pixels**; use rrweb’s *event stream* as your editable command/annotation source, not as the rendered output.

**Verdict for demos:** Pixel video is the primary artifact. DOM replay (rrweb) is an excellent *capture-mode* side-channel — it gives you the structurally-editable interaction stream you can map back onto your command IDs (see B.2).

#### A.2 Playwright as the web unifier — and its limits

Playwright can simultaneously be: (a) the **command player** (it is an automation driver), (b) the **video recorder** (`recordVideo` on the context, or the v1.59 `page.screencast` API), (c) the **cue placement oracle** (`locator.boundingBox()` returns element x/y/width/height for overlay anchoring), and (d) the **human-action recorder** (`playwright codegen`). One dependency fills four slots.

Limits for demo-quality output:

- **Bitrate/resolution:** Per Playwright GitHub Issue #31424, for Chromium-based browsers the “target bitrate = 1Mbit/s is hardcoded… limited to one thread and target cpu usage is 50%,”  and the Playwright Videos docs confirm video “defaults to the viewport size scaled down to fit 800x800,”  producing visibly poor 1080p output. There is no user-facing quality knob (open issues #31424, #10855, #7141). One team reported 5–10 minute render stalls after context close. 
- **WebM only / post-close availability:** Video is VP8/VP9 WebM and is only flushed when the context/page closes — awkward for live pipelines.
- **Mitigation:** For hero/marketing-grade output, drive Playwright as the *player* but capture pixels with **OBS** or **ffmpeg** at full resolution/framerate, OR use the v1.59 `screencast` API (CDP screencast under the hood) which gives finer control and the `onFrame` stream.

#### A.3 Desktop apps — capture + element location

- **Pixels:** ffmpeg with platform grabbers — `gdigrab`/`ddagrab` (Windows; ddagrab is GPU/Desktop-Duplication and handles 4K60), `x11grab` (Linux/Xorg; Wayland needs `wf-recorder`), `avfoundation` (macOS, needs `-capture_cursor 1`).  Or **OBS Studio** remote-controlled via WebSocket v5 (built into OBS ≥ 28) using **`obsws-python`** — `cl.start_record()` / `cl.stop_record()`,  scene control, event callbacks.
- **Element bounds:** **pywinauto** (BSD-3) drives Windows via `win32` and `uia` backends  and exposes `rectangle()` per control; Linux AT-SPI is exposed through `AtspiElementInfo` (rectangle of element);  macOS uses the Apple Accessibility (AX) API. Note pywinauto’s own AT-SPI/macOS support is partial/in-progress  — for cross-platform desktop you may bind the native accessibility libraries (e.g., `libatspi.so` via ctypes) directly.
- **Level-2 difficulty:** On web, a cue is a `pointer-events:none` DOM overlay anchored to a `boundingBox()` — trivial. On desktop you must paint a **transparent, click-through OS-level overlay window** positioned over the target app and keep it synced to window moves/scrolls. This is materially harder, OS-specific, and is the single biggest reason the web and desktop stacks diverge.

### B. Action / macro recording (capture mode)

#### B.1 Tools that record human actions into editable scripts

- **Playwright codegen:** records clicks/fills/navigation/assertions and emits runnable JS/TS/Python/C#, preferring resilient `getByRole`/`getByText`/`getByTestId` locators. Caveat: raw output captures *everything* including exploratory mistakes — per Playwright codegen guidance, “the raw output produced by Codegen does require some human refinement.” 
- **Selenium IDE / browser-extension recorders:** similar record-and-export, broader-but-more-brittle selectors.
- **rrweb interaction stream:** captures a typed event vocabulary — `MouseInteraction` (click, etc.), input, scroll, mouse-move, viewport — as JSON with microsecond timestamps.

#### B.2 Cleanest interception point for “capture mode”

rrweb’s **`record.addCustomEvent(tag, payload)`** is the seam: while rrweb records the raw DOM interaction stream, you simultaneously emit a *custom event* carrying your own command ID and parameters at each dispatch. On replay, `replayer.on('custom-event', …)`  (and the typed `EventType.Custom = 5`)  lets you read those back. This means **your command-dispatch layer is the source of truth** and rrweb is just the time-base: you intercept at the dispatcher (where you already know the command ID), tag the rrweb timeline, and you get a perfectly aligned (interaction-stream ↔ command-stream) pair. For web, Playwright’s `screencast.showActions()` is the equivalent “annotate each action” hook on the *playback/render* side.

### C. Visual cues / overlays (Level 2)

#### C.1 Guidance-overlay libraries

|Library                     |License              |Size         |Reusable as cue layer?                                                             |Notes                                                                                               |
|----------------------------|---------------------|-------------|-----------------------------------------------------------------------------------|----------------------------------------------------------------------------------------------------|
|**driver.js**               |MIT                  |~5 KB gzipped|**Best** — it is “more than a tour library… wherever you need some sort of overlay”|Spotlight/dim-background/highlight any element; vanilla JS; fewest accessibility violations to fight|
|**Shepherd.js**             |MIT (formerly AGPL)  |~25 KB       |Yes — minimal default styling, built to look native                                |Built on Floating UI; framework wrappers; best when cues must match design system                   |
|**intro.js**                |**AGPL / commercial**|~12–29 KB    |Usable but licensing trap                                                          |Worst accessibility in 2026 benchmark; avoid for proprietary unless licensed                        |
|**Reactour / React Joyride**|MIT                  |larger       |React-only; whole-tour frameworks                                                  |Fight the framework if you only want a cue primitive                                                |

For a **cue-rendering layer** (not a tour), wrap **driver.js** for spotlights/rings and render tooltips/callouts yourself anchored to `boundingBox()`. Shepherd is the upgrade when callouts must be on-brand.

#### C.2 Synthetic cursor, zoom/pan, cinematic motion

Arcade/Storylane produce smooth cursor movement, click ripples, and zoom-to-element with **no proprietary magic** — they composite a synthetic cursor and animate CSS `transform` (translate/scale). Open-source building blocks:

- **Motion** (formerly Framer Motion; renamed mid-2025, MIT) — springs, gestures, and a production-grade **FLIP** layout-animation engine (`layout` / `layoutId`) that animates “slow” layout changes via “fast” `transform` properties. Motion animates real elements via transforms (interruptible, non-blocking) vs the native View Transitions API (screenshot crossfade, non-interruptible).
- **FLIP technique** directly: measure First/Last rects, apply Inverse transform, Play to zero — exactly how zoom-to-element is built.
- Synthetic cursor = an absolutely-positioned element animated between `boundingBox()` centers; click ripple = a scale+fade keyframe; zoom = `transform: scale()` on a wrapper with `transform-origin` at the target.

#### C.3 Target stability after UI changes

Demo/test tools keep element references valid via **self-healing locators**. The open-source reference implementation is **Healenium** (Apache-2.0, by EPAM): it wraps the Selenium driver as `SelfHealingDriver`, stores a baseline DOM/locator history in PostgreSQL, and on `NoSuchElementException` compares the stored DOM tree to the current page using the **Longest Common Subsequence (LCS) algorithm enhanced with gradient-boosted, ML-identified priorities** (per EPAM SolutionsHub), then generates ranked candidate locators with a configurable confidence threshold (`score-cap`, e.g. 0.5 = heal when ≥50% match).  Commercial tools (Testim “Smart Locators,” mabl) generalize this to **weighted multi-attribute scoring** — id/class/text/ARIA-role/position/visual fingerprint scored simultaneously, highest-confidence match wins.  Playwright takes a different stance: **resilience by design** (prefer `getByRole`/`getByTestId`, auto-wait/retry) rather than runtime locator-swapping; its docs state “Testing by test ids is the most resilient way of testing.”  For this system: store **multiple candidate selectors + last-known bounding box** per command target, re-resolve by selector first, fall back to scored candidates, and re-resolve the bounding box after capture/scroll so cues stay anchored.

### D. Narration: transcription + TTS

#### D.1 STT and TTS options

**STT (speech-to-text), for TIMED text:**

|Tool              |License           |Word-level timestamps                      |Notes                                                                                                                             |
|------------------|------------------|-------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
|**WhisperX**      |BSD-4-Clause      |**Yes** — forced alignment (wav2vec2) + VAD|Default for timed captions; README claims “70x realtime transcription using whisper large-v2”; calls faster-whisper under the hood|
|**faster-whisper**|MIT               |via add-on                                 |CTranslate2 engine; fastest baseline                                                                                              |
|**whisper.cpp**   |MIT               |limited                                    |CPU/edge; Remotion Recorder uses it for local captions                                                                            |
|**CrisperWhisper**|(model-card terms)|Yes, verbatim incl. fillers                |When disfluency-accurate timing matters                                                                                           |

**TTS (text-to-speech):**

|Tool                               |License                   |Commercial-safe?       |Notes                                                                  |
|-----------------------------------|--------------------------|-----------------------|-----------------------------------------------------------------------|
|**Piper**                          |MIT                       |Yes                    |CPU/edge, ~10× real-time, no cloning; great default for batch narration|
|**Kokoro (82M)**                   |Apache-2.0                |Yes                    |Efficient, high quality                                                |
|**XTTS-v2 (Coqui)**                |Coqui Public Model License|**No (non-commercial)**|Best cloning (6-sec ref, 17 langs) but license blocks commercial       |
|**Fish Speech**                    |Apache-2.0                |Yes                    |Practical pick for commercial cloning                                  |
|**ElevenLabs / OpenAI TTS / Azure**|hosted/commercial         |Yes (paid)             |Top naturalness; per-character billing                                 |

The **Descript model** (“edit transcript → edit audio”) works because each transcript word is aligned to a media offset; deleting text deletes the corresponding media span  non-destructively. Replicate this with WhisperX word timings → editable transcript → re-synthesize changed spans with TTS.

#### D.2 Timed-text representation & alignment

Round-trip narration as **WebVTT** (web-native, `HH:MM:SS.mmm`, supports cue positioning/`NOTE`/chapters/`STYLE`, CSS `::cue`)  or **SRT** (universal, `HH:MM:SS,mmm`, near-universal NLE support). Conversion is trivial (separator `,`↔`.` + header).  For richer per-word data (confidence, speaker), carry a JSON sidecar with `{word, start, end, confidence}` and *derive* VTT/SRT from it. Align to the video timeline by anchoring cue start/end to capture-clock timestamps; after edits, re-run alignment on the final exported media (not a proxy) to avoid drift. 

### E. Editing & re-render hand-off

#### E.1 Interchange formats

|Format                   |Realistic hand-off target?                 |Notes                                                                                                                                                                      |
|-------------------------|-------------------------------------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
|**OpenTimelineIO (OTIO)**|**Yes — primary**                          |Apache-2.0, Python-native API + JSON; adapters for EDL (cmx_3600), FCP7-XML, FCPX-XML, AAF. “A modern EDL that also includes an API.” Carries the editable demo *timeline*.|
|**rrweb event JSON**     |**Yes — for the command/interaction layer**|Carries the structurally-editable command + annotation stream                                                                                                              |
|**EDL (CMX3600)**        |Partial / inspiration                      |One video track + few audio tracks — too limited for multi-track demos; reachable via OTIO adapter                                                                         |
|**FCPXML**               |Via OTIO adapter                           |Good import path to Premiere/Resolve/FCP; “lite” adapters exist                                                                                                            |
|**WebVTT/SRT**           |Yes — narration track                      |Timed text layer                                                                                                                                                           |

Recommended artifact shape: a JSON document the core owns = `{command_stream[], annotation_timeline[], narration(vtt), media_refs[]}`, with **OTIO emitted for the visual timeline** and **VTT/SRT for narration**. The renderer consumes these; the core never imports the renderer.

#### E.2 Programmatic assembly/render libraries (consumer side)

|Tool                     |License                                                                                       |Model                                                                             |Pairs naturally with                                                                  |
|-------------------------|----------------------------------------------------------------------------------------------|----------------------------------------------------------------------------------|--------------------------------------------------------------------------------------|
|**WebReel (Vercel Labs)**|Apache-2.0                                                                                    |JSON config → headless Chrome → ~60fps frames → cursor/keystroke overlays → ffmpeg|**Closest analog to this system**; demo “is now code,” committable & reviewable in PRs|
|**Remotion**             |Free for individuals & companies ≤3 people; paid Company License at 4+ (Developer Seat $25/mo)|React components as frames; headless-Chromium render                              |Annotation-driven React templates; `<Player>` for web preview                         |
|**Revideo**              |MIT                                                                                           |Motion-Canvas fork + render API                                                   |Automated pipelines; server-side render                                               |
|**Motion Canvas**        |MIT                                                                                           |Imperative TS generator, canvas engine                                            |Hand-crafted explanatory motion                                                       |
|**moviepy / ffmpeg**     |MIT / LGPL-GPL                                                                                |Python clip assembly / CLI                                                        |Python orchestration; final mux                                                       |

**WebReel** deserves emphasis as the design north-star: it is an open-source CLI (github.com/vercel-labs/webreel, Apache-2.0) that records scripted browser demos from a `webreel.config.json`. Per its README: “Define steps in a JSON config (clicks, key presses, drags, pauses) and webreel drives a headless Chrome instance, captures screenshots at ~60fps, and encodes the result with ffmpeg.”  Its action vocabulary (click, type, scroll, drag, screenshot, navigate, hover, select, key, wait, moveTo, pause) and element targeting (visible `text` OR CSS `selector`, optional `within` scoping — “You can use `text` or `selector` (not both). `within` is optional and scopes the search.”)  map almost 1:1 onto the command stream this system already has. It composites cursor + keystroke overlays and its `composite` command can “Re-composite videos from stored raw recordings and timelines without re-recording”  — exactly the “editable artifact, separate final render” split the task describes. The reproducibility framing is explicit: third-party coverage summarizes it as “your demo video is now code. Commit webreel.config.json to your repo. When the UI changes, update the config and re-record. Review demo changes in pull requests just like you review code,”  and the official site frames it as “Configs are committable and reviewable in PRs.” 

### F. Mode-fit recommendations

#### Stack 1 — Web-first (the simple case)

|Slot                |Wrap this                                                               |DI interface (port)                            |
|--------------------|------------------------------------------------------------------------|-----------------------------------------------|
|Command player      |Playwright `page`                                                       |`CommandPlayer.play(cmd)`                      |
|Screen/video capture|Playwright `screencast` (or OBS/ffmpeg for hero quality)                |`Recorder.start()/stop() → media_ref`          |
|Action recording    |Playwright codegen + rrweb `addCustomEvent`                             |`ActionRecorder.record() → command_stream`     |
|Visual cues         |driver.js (spotlight) + Playwright `showOverlay/showActions/showChapter`|`CueRenderer.show(cue, bbox)`                  |
|Narration STT/TTS   |WhisperX + Piper/ElevenLabs                                             |`Transcriber.transcribe()`, `Synthesizer.say()`|
|Re-render hand-off  |emit OTIO + VTT → WebReel/Remotion                                      |`RenderTarget.export(artifact)`                |

**Biggest simplification:** Playwright collapses player + capture + cue-anchoring + action-recording into one dependency. The whole core shrinks to “orchestrate a command stream, tag a timeline, emit an artifact.” You wrap exactly one heavy dependency and inject narration + render.

#### Stack 2 — Web + desktop

|Slot          |Web                    |Desktop                                                        |DI interface                   |
|--------------|-----------------------|---------------------------------------------------------------|-------------------------------|
|Command player|Playwright             |your existing dispatcher + pywinauto/AX                        |`CommandPlayer`                |
|Capture       |Playwright/OBS         |OBS via `obsws-python` (or ffmpeg gdigrab/x11grab/avfoundation)|`Recorder`                     |
|Element bounds|`boundingBox()`        |pywinauto `.rectangle()` / AT-SPI / AX                         |`ElementLocator.bounds(target)`|
|Cues          |DOM overlay (driver.js)|**click-through OS overlay window**                            |`CueRenderer` (two impls)      |
|Narration     |WhisperX + Piper       |same                                                           |`Transcriber`/`Synthesizer`    |
|Render        |OTIO + VTT → renderer  |same                                                           |`RenderTarget`                 |

**Biggest simplification:** standardize on **OBS via obsws-python** as the *single* capture backend for both web and desktop (OBS captures a browser or any window identically), so only the **element-bounds** and **cue-rendering** ports need per-platform implementations. Everything downstream (artifact, narration, render) is platform-agnostic.

### “Wrap, don’t rebuild” — the injected interface shapes

Each port is a thin facade; the type to wrap and the boundary:

- **`CommandPlayer`** — wraps Playwright `page` (web) or your dispatcher + pywinauto (desktop). Method: `play(command) -> result`. The core only knows command IDs and params, never `page`.
- **`Recorder`** — wraps Playwright `screencast`, OBS (`obsws-python`), or ffmpeg. Methods: `start(opts)`, `stop() -> media_ref`. Swappable purely on the quality threshold (see thresholds below).
- **`ActionRecorder`** — wraps Playwright codegen + rrweb. Method: `record() -> command_stream`. Intercept at the dispatcher and tag rrweb with `addCustomEvent`.
- **`ElementLocator`** — wraps `boundingBox()` / pywinauto `.rectangle()` / AT-SPI / AX. Method: `bounds(target) -> rect`. Stores multiple candidate selectors for self-healing.
- **`CueRenderer`** — wraps driver.js + Playwright overlay (web) or an OS overlay window (desktop). Method: `show(cue, rect)`.
- **`Transcriber` / `Synthesizer`** — wrap WhisperX and Piper/ElevenLabs. Methods: `transcribe(audio) -> timed_words`, `say(text) -> audio`.
- **`RenderTarget`** — wraps WebReel/Remotion/moviepy. Method: `export(artifact) -> video`. The core emits OTIO + VTT + JSON; the adapter maps fields.

-----

## Recommendations

**Stage 0 — Lock the core contracts first (week 1).** Define the serializable artifact (`command_stream`, `annotation_timeline`, `narration` as VTT, `media_refs`) and the seven ports above. No vendor types cross these boundaries. This is the “wrap, don’t rebuild” firewall.

**Stage 1 — Ship web-first on Playwright (weeks 2–4).** Wrap Playwright for player + capture + action-recording + cue-anchoring. Use `screencast` for capture and overlays; if QA flags the 1 Mbit/s / 800×800 quality ceiling, switch the `Recorder` impl to OBS/ffmpeg with zero core changes (that is the payoff of the port). Emit OTIO + VTT.

**Stage 2 — Add narration (week 5).** Inject WhisperX (`Transcriber`) for word-timed text and Piper (`Synthesizer`, MIT, commercial-safe) as default; allow an ElevenLabs adapter for premium voices. Build the Descript-style “edit transcript → re-synthesize changed spans” loop on the VTT word timings.

**Stage 3 — Hand off to a renderer (week 6).** Target **WebReel** (Apache-2.0) or **Remotion** as the first `RenderTarget`. Because WebReel’s JSON action vocabulary mirrors your command stream, the adapter is largely a field-mapping.

**Stage 4 — Add desktop only if demanded.** Add OBS-via-obsws-python capture (already platform-agnostic) and the two hard per-platform ports: `ElementLocator` (pywinauto/AT-SPI/AX) and an OS-level click-through `CueRenderer`. Budget extra time for the overlay window.

**Decision thresholds (what would change the recommendation):**

- *If* demos are web-only and ≤1080p is acceptable → stay on Playwright `screencast` alone (no OBS).
- *If* you need ≥1080p/60 hero output → swap `Recorder` to OBS/ffmpeg.
- *If* you ship a commercial product → avoid intro.js (AGPL) and XTTS-v2 (non-commercial license); use driver.js/Shepherd (MIT) and Piper/Kokoro/Fish Speech (MIT/Apache).
- *If* your company exceeds 3 people and render volume makes Remotion’s Company License material → switch `RenderTarget` to Revideo/Motion Canvas (MIT) or moviepy/ffmpeg.

-----

## Caveats

- **rrweb temporal drift & non-DOM content:** rrweb replays *instructions*, not pixels, so replays can show today’s data and break on canvas/WebGL/nested iframes — keep it as the editable *command-stream* side-channel, not the rendered deliverable.
- **Playwright video quality is a known, unresolved limitation** (hardcoded 1 Mbit/s bitrate per Issue #31424, 800×800 default downscale, single-thread); treat the external-capturer fallback as likely-needed for marketing-grade output, not optional.
- **Licensing landmines:** intro.js is AGPL/commercial; XTTS-v2 is non-commercial (Coqui Public Model License); Remotion is free only for individuals and companies up to three people (paid Company License at 4+).  These are easy to adopt accidentally and expensive to unwind.
- **Maintenance risk:** Coqui (the company behind XTTS/Coqui TTS) shut down in early 2024 — the project is community-maintained; prefer Piper/Kokoro/Fish for longevity. pywinauto’s macOS/AT-SPI support is partial/long-roadmap; the desktop element-bounds story is the least mature part of the stack.
- **“Reelee” identification:** the task’s “Reelee” almost certainly refers to **WebReel** (Vercel Labs, Apache-2.0, github.com/vercel-labs/webreel); the design guidance treats it as the canonical hand-off target. If “Reelee” is a distinct internal tool, the same OTIO/VTT/JSON artifact contract applies unchanged.
- **Self-healing is structural, not semantic:** Healenium’s LCS comparison is purely structural; a major redesign can still defeat it. Always store stable `data-testid`/`data-tour` attributes on demo targets as the primary anchor.

-----

## REFERENCES

[1] [Playwright — Videos](https://playwright.dev/docs/videos)
[2] [Playwright GitHub Issue #31424 — video recording quality control](https://github.com/microsoft/playwright/issues/31424)
[3] [Playwright GitHub Issue #10855 — better video quality](https://github.com/microsoft/playwright/issues/10855)
[4] [Playwright GitHub Issue #7141 — video resolution options](https://github.com/Microsoft/playwright/issues/7141)
[5] [Playwright — Screencast API (class)](https://playwright.dev/docs/api/class-screencast)
[6] [Playwright Release v1.59.0](https://github.com/microsoft/playwright/releases/tag/v1.59.0)
[7] [Playwright Release Notes](https://playwright.dev/docs/release-notes)
[8] [Playwright CLI Video Recording (KnightLi)](https://www.knightli.com/en/2026/04/15/playwright-cli-video-recording/)
[9] [TestDino — Playwright Screencast](https://testdino.com/blog/playwright-screencast)
[10] [TestDino — Playwright 1.59 Release Guide](https://testdino.com/blog/playwright-release-guide)
[11] [Playwright — Test generator (codegen)](https://playwright.dev/docs/codegen)
[12] [BrowserStack — How to Use Playwright Codegen](https://www.browserstack.com/guide/how-to-use-playwright-codegen)
[13] [Autify — Playwright Codegen Guide](https://autify.com/blog/playwright-codegen)
[14] [Checkly — Record Automation Scripts Using Playwright Codegen](https://www.checklyhq.com/docs/learn/playwright/codegen/)
[15] [Browserbase — This week we fixed the worst part of Browserbase (rrweb → pixel)](https://www.browserbase.com/blog/session-recordings)
[16] [rrweb — GitHub](https://github.com/rrweb-io/rrweb)
[17] [rrweb — Custom Event recipe (addCustomEvent)](https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/custom-event.md)
[18] [rrweb — Dive into event types](https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/dive-into-event.md)
[19] [BrightCoding — Deep Dive with rrweb](https://www.blog.brightcoding.dev/2025/09/01/record-and-replay-user-sessions-on-the-web-a-deep-dive-with-rrweb/)
[20] [Hacker News — How does rrweb/OpenReplay work](https://news.ycombinator.com/item?id=32658825)
[21] [Sentry — Session Replay for Web](https://docs.sentry.io/product/explore/session-replay/web/)
[22] [obsws-python — PyPI](https://pypi.org/project/obsws-python/)
[23] [obs-websocket — GitHub](https://github.com/obsproject/obs-websocket)
[24] [aatikturk/obsws-python — GitHub](https://github.com/aatikturk/obsws-python)
[25] [OBS Forums — Start/stop OBS recording remotely via Python](https://obsproject.com/forum/threads/start-stop-obs-recording-remotely-via-python-or-similar.179398/)
[26] [FFmpeg Cookbook — Screen Recording (Windows/macOS/Linux)](https://ffmpeg-cookbook.com/en/articles/screen-recording/)
[27] [Xabe.FFmpeg — Cross-Platform Desktop Capture](https://ffmpeg.xabe.net/documentation/desktop.html)
[28] [FFmpeg wiki — Quick How-To: recording desktop](https://gist.github.com/swipswaps/267cc8b0561ff0fbe3c8ce9811147437)
[29] [pywinauto — Getting Started Guide](https://pywinauto.readthedocs.io/en/latest/getting_started.html)
[30] [pywinauto — AtspiElementInfo (Linux AT-SPI)](https://pywinauto.readthedocs.io/en/atspi/code/pywinauto.linux.atspi_element_info.html)
[31] [pywinauto — GitHub](https://github.com/pywinauto/pywinauto)
[32] [Inline Manual — Driver.js vs Intro.js vs Shepherd.js vs Reactour](https://inlinemanual.com/blog/driverjs-vs-introjs-vs-shepherdjs-vs-reactour/)
[33] [userTourKit — 2026 React tour library benchmark](https://usertourkit.com/blog/react-tour-library-benchmark-2026)
[34] [Userorbit — Best Open-Source Product Tour Libraries](https://userorbit.com/blog/best-open-source-product-tour-libraries)
[35] [LogRocket — 7 best product tour JavaScript libraries](https://blog.logrocket.com/best-product-tour-js-libraries-frontend-apps/)
[36] [npm-compare — driver.js vs intro.js vs shepherd.js vs vue-tour](https://npm-compare.com/driver.js,intro.js,shepherd.js,vue-tour)
[37] [Motion — JavaScript & React animation library](https://motion.dev/)
[38] [Motion — Layout Animation (FLIP & Shared Element)](https://motion.dev/docs/react-layout-animations)
[39] [Nan.fyi — Inside Framer’s Magic Motion (FLIP)](https://www.nan.fyi/magic-motion)
[40] [Refine — Framer Motion / Motion guide](https://refine.dev/blog/framer-motion/)
[41] [Saltfish — Storylane vs Arcade](https://www.saltfish.ai/blog/storylane-vs-arcade)
[42] [Arcade Knowledge Base — Design (cursor, pan & zoom)](https://docs.arcade.software/kb/build/interactive-demo/edit/design)
[43] [Modal — Choosing between Whisper variants](https://modal.com/blog/choosing-whisper-variants)
[44] [Towards AI — Whisper Variants Comparison](https://towardsai.net/p/machine-learning/whisper-variants-comparison-what-are-their-features-and-how-to-implement-them)
[45] [WhisperX — Time-Accurate Speech Transcription (arXiv)](https://arxiv.org/pdf/2303.00747)
[46] [CrisperWhisper — faster_CrisperWhisper (Hugging Face)](https://huggingface.co/nyrahealth/faster_CrisperWhisper)
[47] [Apatero — Open Source Text to Speech 2026](https://apatero.com/blog/open-source-text-to-speech-models-beyond-elevenlabs-2026)
[48] [PromptQuorum — Local TTS & Voice Cloning 2026](https://www.promptquorum.com/power-local-llm/local-tts-voice-cloning-piper-coqui-xtts)
[49] [CodeSOTA — Best TTS Models 2026 (licensing)](https://www.codesota.com/guides/tts-models)
[50] [BentoML — Best Open-Source TTS Models 2026](https://www.bentoml.com/blog/exploring-the-world-of-open-source-text-to-speech-models)
[51] [Thomas Derflinger — Analyzing Open Source TTS Alternatives](https://tderflinger.com/text-to-talk-analyzing-open-source-tts-alternatives)
[52] [W3C — WebVTT: The Web Video Text Tracks Format](https://www.w3.org/TR/webvtt1/)
[53] [MDN — WebVTT API](https://developer.mozilla.org/en-US/docs/Web/API/WebVTT_API)
[54] [MDN — Web Video Text Tracks Format (WebVTT)](https://developer.mozilla.org/en-US/docs/Web/API/WebVTT_API/Web_Video_Text_Tracks_Format)
[55] [Vocova — SRT vs VTT](https://vocova.app/blog/srt-vs-vtt)
[56] [GoTranscript — Fix Timestamps in Auto-Generated Transcripts](https://gotranscript.com/en/blog/fix-timestamps-timecodes-auto-generated-transcripts)
[57] [Descript Help — Edit like a doc](https://help.descript.com/hc/en-us/articles/15726742913933-Edit-like-a-doc)
[58] [Descript Help — Add a file to the script](https://help.descript.com/hc/en-us/articles/33828200519949-Add-a-file-to-the-script)
[59] [OpenTimelineIO — GitHub](https://github.com/AcademySoftwareFoundation/OpenTimelineIO)
[60] [OpenTimelineIO — Adapters (EDL/FCP7-XML/FCPX-XML/AAF)](https://opentimelineio.readthedocs.io/en/stable/)
[61] [OpenTimelineIO in Blender — Blender Studio](https://studio.blender.org/blog/opentimelineio-in-blender/)
[62] [otio-fcpx-xml-lite-adapter — PyPI](https://pypi.org/project/otio-fcpx-xml-lite-adapter/)
[63] [Remotion — Make videos programmatically](https://www.remotion.dev/)
[64] [Remotion vs Motion Canvas (official compare)](https://www.remotion.dev/docs/compare/motion-canvas)
[65] [Remotion vs Motion Canvas vs Revideo (PkgPulse)](https://www.pkgpulse.com/blog/remotion-vs-motion-canvas-vs-revideo-programmatic-video-2026)
[66] [BuildPilot — Remotion vs Motion Canvas vs Revideo (2026)](https://trybuildpilot.com/363-remotion-vs-motion-canvas-vs-revideo-2026)
[67] [Revideo — GitHub](https://github.com/midrender/revideo)
[68] [Remotion Recorder (whisper.cpp captions)](https://www.remotion.dev/docs/recorder)
[69] [WebReel — Vercel Labs (Vibe Sparking writeup)](https://www.vibesparking.com/en/blog/awesome-tools/2026-03-04-vercel-webreel-scripted-browser-demo-videos/)
[70] [Healenium-web — GitHub](https://github.com/healenium/healenium-web)
[71] [Healenium — official site](https://healenium.io/)
[72] [EPAM SolutionsHub — Healenium (LCS + ML algorithm)](https://solutionshub.epam.com/)
[73] [Playwright — Locators (resilience by design)](https://playwright.dev/docs/locators)
[74] [JSON2Video — Programmatic Video guide (Remotion/MoviePy/FFmpeg)](https://json2video.com/video-automation/programmatic-video/)