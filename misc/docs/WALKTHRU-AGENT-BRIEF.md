# Build Brief — `thorwhalen/walkthru`

**For:** the coding agent that will scaffold and populate this repository.
**From:** Thor Whalen.
**Read first, then plan, then build.**

-----

## 0. How to use this brief

You are receiving three documents:

1. **This brief** — the decisions, constraints, and repo conventions.
1. **`demo2reel 01 …` — Tooling & Capability Survey.** Which external tools/libraries fill
   each capability slot, their trade-offs, licenses, and the wrap-don’t-rebuild interface
   shapes. *Read it in full before choosing any dependency.*
1. **`demo2reel 02 …` — The Demo Document (data model & open-closed architecture).** The
   proposed schema, the `play()` core, the generative/capture duality, the plugin seams,
   the renderer hand-off, and the MVP/defer staging. *Read it in full before designing the
   schema or the core.*

This brief states conclusions we have already reached. The two reports justify them and add
detail. **Where this brief and a report agree, treat it as decided. Where you, looking at the
actual ecosystem code, find a better path, you have authority to deviate — but you must say so
explicitly in `DECISIONS.md` (see §7) with your reasoning.** We are deferring final judgment to
you precisely because you can see `reelee`, `acture`, `zodal`, and the existing command-dispatch
layer, and we cannot from here. Do not silently diverge; do not slavishly follow. Plan first.

**Your first deliverable is a plan, not code.** Read everything, inspect the ecosystem repos you
have access to, then produce `PLAN.md` and `DECISIONS.md`. Only then scaffold.

-----

## 1. What `walkthru` is

A library that turns **a sequence of application commands** into an **editable, re-renderable
demo/tour artifact** — and the engine that plays such a sequence while observers record video,
draw visual cues, and narrate. It is the macro-replay/recording consumer of an existing
**command-dispatch architecture** (every operation is already a named, typed, schema-defined
command `{id, params}` in a central registry; a macro is already a serializable list of these).

Two operating modes, **one data model and one engine**:

- **Generative mode:** an author supplies a Demo Document (commands + annotations); `walkthru`
  plays it while recording, with optional visual cues (highlight the acted-on element, zoom/pan,
  synthetic cursor, pauses, narration).
- **Capture mode:** a human operates the app manually; `walkthru` records the video **and** the
  underlying command stream **and** annotations, producing the *same* Demo Document artifact.

The actual final video rendering is done by **other tools** (the `reelee` ecosystem, Remotion,
moviepy/ffmpeg, etc.). `walkthru` owns the **representation** (the Demo Document) and the
**playback/capture engine**; it hands a validated artifact to a renderer. **Owning
representation, not pixels, is the load-bearing boundary of the whole design.**

-----

## 2. Non-negotiable design principles

These are firm. Everything else is open to your judgment.

1. **Dependency inversion, ecosystem-biased but ecosystem-independent.** Default and bias toward
   our ecosystem (`reelee`, `acture`, `zodal`, the existing command layer), but depend on it only
   through injected ports/interfaces. `walkthru`’s core must run, be tested, and be published with
   **zero hard dependency** on any ecosystem package. Ecosystem integration ships as adapters in
   separate, optional modules/packages. Someone outside our ecosystem must be able to `pip install walkthru` / `npm i acture-walkthru` and use the core with their own adapters.
1. **A tiny pure core.** The core is one higher-order function — `play(demoDoc, executor, observers)` — that walks the document and emits lifecycle events. It never records, renders, or
   speaks. (Report 02 §B.1.) All effects are injected observers/ports.
1. **One schema as SSOT.** A single schema is the source of truth for the Demo Document, serving
   both modes; the only difference between modes is *who fills it in*. JSON is the wire format.
   (Report 02 §A.6.)
1. **Open–closed via the seams we already know.** Reuse the command layer’s
   **registry + middleware** mechanisms for cue handlers, observers, and exporters rather than
   inventing a new extension paradigm. (Report 02 §B.3.)
1. **Progressive disclosure.** Simple demos are trivial to author; rich choreography is possible
   but never required. Match Thor’s standing conventions (functional over OOP, declarative over
   imperative, composition over inheritance, facades, SSOT, DI, plugin architecture) — without
   dogma.
1. **YAGNI / rule of three, enforced.** Build the MVP schema and engine; *reserve but do not
   implement* branching, parallel cross-section cue choreography, effects graphs, B-roll
   compositing. The dominant failure mode is the **inner-platform effect** — re-inventing a video
   editor inside the schema. The schema models *intent and annotation*; all compositing, easing
   curves, and transitions live in the renderer. (Report 02 §C, §Recommendations.)

-----

## 3. The data model — what to build (and what to reserve)

Follow Report 02 §A and its “Minimal viable schema” (§Recommendations, Stage 1). Summary of the
decided shape — confirm against the report, then refine against `zodal`/the command layer:

- **`DemoDocument { id, meta, sections: Section[] }`**
- **`Section { id, title?, steps: Step[] }`**
- **`Step` is a discriminated union:** `CommandStep { command:{id,params}, timing:{duration, holdAfter?}, cueRefs?, narrationRef? }` and `Beat { kind, timing, … }` (non-command beats: pure
  pause, title/text card, B-roll insert). Do **not** force these into one over-parameterized type
  bristling with optional flags — keep a small discriminated union (Report 02 §C, “wrong
  abstraction for step”).
- **Separate tracks referenced by anchor, not a single flat list:** **cues**, **narration**,
  **camera**. Cues/narration/camera have different lifetimes and cardinalities than commands and
  must not be crammed into the command. (Report 02 §A.2, §A.4–A.5.)
- **Relative, anchor-based time.** Each Step/Section carries a *local* `duration` (+ optional
  `holdAfter`); global time is *derived by composition*. Cues/narration anchor to
  `(stepId, localOffset)`. **No absolute timestamps in the SSOT** — they couple every edit to a
  global recompute and bloat diffs. Represent durations as ms or a rational quantity; let the
  renderer convert to frames. (Report 02 §A.3.)
- **Cue types limited to the proven five for MVP:** highlight ring, spotlight/dim-surround,
  hotspot, callout/tooltip, synthetic cursor. Each is a typed variant with a **target reference**.
  (Report 02 §A.4.)
- **Target reference is a resilient, prioritized locator**, not a single brittle CSS path:
  `{ primary, fallbacks[], bbox?, scrollAnchor? }`. Re-resolve by primary, fall back down the
  list; treat any self-healing as a *logged suggestion for human review*, never a silent SSOT
  rewrite. (Report 02 §A.4, §C.)
- **Narration follows the Descript principle** — text is the editable SSOT, media follows the
  text: `NarrationSegment { id, text, anchor:{stepId,localOffset,duration}, audioRef?, tts?, wordTimings? }`. Editing `text` invalidates `audioRef` and triggers re-synthesis. Round-trips to
  WebVTT/SRT for free. (Report 02 §A.5.)
- **Reserve (type-level seam, no traversal code): branching** (`next: stepId | Branch`). This is
  the single feature most likely to trigger the inner-platform effect. (Report 02 §Recommendations
  Stage 3.)

**Schema technology — your call, but here is the bias.** Report 02 recommends Zod because the
command layer already uses it; the frontend stack here is JS/TS + Zod. **`zodal` is in our
ecosystem and is the presumptive schema layer — inspect it and decide** whether the Demo Document
schema should be authored in `zodal`, plain Zod, or a `zodal`-on-Zod arrangement, and how to emit
JSON Schema for the renderer hand-off. On the Python side, decide the mirror representation
(typed dataclasses / pydantic / generated-from-JSON-Schema) consistent with Thor’s
python-coding-standards. **The SSOT must round-trip losslessly between the TS and Python sides via
JSON.** Document the choice in `DECISIONS.md`.

-----

## 4. The engine and the ports — what to build

Follow Report 02 §B and Report 01 §“Wrap, don’t rebuild”.

- **Core:** `play(demoDoc, executor, observers) -> Outcome`. Pure walk + lifecycle emission.
  Lifecycle protocol (Report 02 §B.1): `onDemoStart/End`, `onSectionEnter/Exit`, `onStepEnter` →
  `beforeCommand` → `afterCommand`|`onCommandError` → `onStepExit`, `onCueBegin/End`,
  `onNarration`, `onBeat`. Observers are pure subscribers composed as a list — recorder, overlay,
  narrator, pacer, logger are all just observers.
- **Driver inversion = one core, two modes.** Abstract the command sequence behind a
  **`CommandSource`**: a pull-iterator for generative mode (executor drives), a push-stream adapter
  for capture mode (human drives; an interception observer taps the live command-dispatch stream
  and *emits* Steps into a fresh Demo Document). The lifecycle protocol — and every observer — is
  identical in both modes. (Report 02 §B.2.) **Inspect the command-dispatch layer to find the
  cleanest interception point** for capture mode.
- **The injected ports (facades; no vendor type crosses these boundaries):**
  `CommandPlayer.play(command)→result`, `Recorder.start()/stop()→media_ref`,
  `ActionRecorder.record()→command_stream`, `ElementLocator.bounds(target)→rect`,
  `CueRenderer.show(cue, rect)`, `Transcriber.transcribe(audio)→timed_words`,
  `Synthesizer.say(text)→audio`, `RenderTarget.export(artifact)→video`. (Report 01
  §“Wrap, don’t rebuild”, §F.)
- **Plugin seams (reuse registry + middleware):** new **cue type** → registry of cue handlers
  (`cueType → {validate, render}`) + schema variant; new **recorder/narrator** → strategy behind a
  port, injected; new **export target** → registry of exporters + visitor over the document; new
  **command** → already handled by the existing command registry, no `walkthru` change;
  cross-cutting concerns (timing, redaction, analytics) → middleware around `executor` and around
  observers. (Report 02 §B.3.)

-----

## 5. Tooling defaults (bias; confirm against Report 01 and the ecosystem)

Report 01 is the authority on these; it includes versions, licenses, and known limitations. Do
not pull a dependency without reading its row there. Defaults we lean toward:

- **Web is the first target, and Playwright is the web unifier** — it can be `CommandPlayer`,
  `Recorder` (its `screencast`/video), `ElementLocator` (`boundingBox()`), and `ActionRecorder`
  (codegen) at once, collapsing four ports into one wrapped dependency. **But wrap it behind the
  ports above; never let Playwright types leak into the core.** Note its documented quality ceiling
  (Report 01 §A.2: hardcoded ~1 Mbit/s, ~800×800 default) — the payoff of the `Recorder` port is
  that you can swap to **OBS (`obsws-python`)/ffmpeg** for hero-quality output with zero core
  changes.
- **Capture-mode side-channel:** rrweb is the editable interaction time-base; its
  `addCustomEvent` is the seam to tag the timeline with *your* command IDs — but **the
  command-dispatch layer is the source of truth**, rrweb is just the aligned time base. Pixel video
  remains the primary deliverable; rrweb is the structural side-channel, not the rendered output.
  (Report 01 §A.1, §B.2.)
- **Visual cues:** wrap **driver.js** (MIT, ~5 KB) for spotlight/highlight; render callouts
  anchored to `boundingBox()`. Synthetic cursor / zoom-pan / ripples are CSS `transform` + FLIP
  (optionally **Motion**, MIT) — not proprietary magic. **Avoid intro.js (AGPL/commercial trap)
  for anything proprietary.** (Report 01 §C.)
- **Narration:** STT default **WhisperX** (timed/word-level); TTS default **Piper** (MIT,
  commercial-safe) with a hosted adapter (ElevenLabs/OpenAI/Azure) for premium voices. **Each
  heavy node is a strategy with a cheap/draft impl and a heavy/final impl behind one port** — e.g.
  browser Web Speech API or in-browser Kokoro.js for the live draft loop, hosted/neural for final.
  Timed text round-trips as WebVTT/SRT. (Report 01 §D.)
- **Renderer hand-off:** primary artifact is the **frozen JSON projection of the Demo Document**,
  validated against the published schema, consumed as renderer “input props” (the Remotion model;
  good proxy for `reelee`). **OTIO** and **WebVTT/SRT** are *export targets* to add only when an
  NLE round-trip or caption need is real. The renderer must be free to ignore anything it doesn’t
  understand and still produce a coherent video. (Report 01 §E; Report 02 §B.4.) **Inspect
  `reelee`’s actual input contract and write the first `RenderTarget` adapter against it** — Report
  02’s Caveats note Reelee could not be identified from public sources, so the real contract
  supersedes the Remotion proxy; only the field-mapping adapter changes.

-----

## 6. Repository: `thorwhalen/walkthru` — populate it

Host **both** the Python and the frontend work here.

- **PyPI package name:** `walkthru` (available).
- **npm package name:** `acture-walkthru` (the bare `walkthru` is taken on npm; the `acture-`
  prefix reflects the close tie to `acture`). Scope/prefix consistently.

**Structure** (propose the final layout in `PLAN.md`; this is the intended shape, adapt to
Thor’s python-package-architecture and to a clean TS monorepo convention):

```
walkthru/
  README.md                     # what it is, the two modes, the boundary, quickstart
  PLAN.md                       # YOUR plan (deliver before scaffolding)
  DECISIONS.md                  # every deviation from this brief + every open judgment call
  LICENSE                       # pick a permissive license consistent with the ecosystem
  py/                           # Python side — PyPI "walkthru"
    pyproject.toml              # per python-package-architecture conventions
    src/walkthru/
      __init__.py
      core/                     # pure: play(), lifecycle, CommandSource, schema (SSOT mirror)
      ports/                    # abstract ports (Protocols): Recorder, CueRenderer, …
      adapters/                 # OPTIONAL impls, isolated: playwright/, obs/, whisperx/, piper/, …
      ecosystem/                # OPTIONAL ecosystem adapters: reelee/, acture/, zodal/
    tests/
  ts/                           # Frontend side — npm "acture-walkthru"
    package.json
    src/
      core/                     # pure: play(), lifecycle, CommandSource, the Zod/zodal SSOT
      ports/                    # port interfaces
      adapters/                 # playwright/, driverjs/, motion/, webspeech/, kokoro/, …
      ecosystem/                # reelee/, acture/, zodal/ adapters (optional)
    tests/
  schema/                       # the shared SSOT: JSON Schema emitted from the canonical schema,
                                # plus fixtures used to prove TS<->Python JSON round-trip
  examples/                     # a runnable web-first generative demo + a capture-mode demo
```

**Core/adapter firewall is mandatory:** `core/` and `ports/` import nothing from `adapters/` or
`ecosystem/`. Adapters depend on ports, never the reverse. The dependency graph must make it
impossible for an ecosystem package or a vendor SDK to become a hard dependency of the core. Add a
test/CI check that the core imports cleanly with no optional deps installed.

**Cross-language SSOT:** the Demo Document schema is authored once (your call where — see §3) and
the *other* language consumes the emitted JSON Schema. Ship fixtures in `schema/` and a test that
serializes a Demo Document in one language and validates/round-trips it in the other.

-----

## 7. Deliverables and order of work

**Deliverable 1 — `PLAN.md` (before any code).** After reading both reports and inspecting the
ecosystem repos you can see (`reelee`, `acture`, `zodal`, the command-dispatch layer):

- The chosen schema technology and where the SSOT is authored (TS-Zod/`zodal` vs Python-first),
  and the round-trip strategy.
- The final repo layout and the package boundaries.
- The MVP cut: exactly which schema fields, which five cue types, which ports, which single
  adapter per port you’ll implement first. Bias to **web-first on Playwright** unless inspection of
  the ecosystem says otherwise.
- The capture-mode interception point you found in the command-dispatch layer.
- The `reelee` input contract you found and how the first `RenderTarget` adapter maps to it.
- What you are explicitly **reserving but not building** (branching, etc.).

**Deliverable 2 — `DECISIONS.md`.** Every place you deviate from this brief or either report, with
the reasoning and what you saw in the code that justified it. Also every genuinely open call you
made. This is how we audit your judgment; be candid, not deferential.

**Deliverable 3 — the populated repo.** Implement the MVP from `PLAN.md`:

1. The SSOT schema (one language) + emitted JSON Schema + the mirror + round-trip test.
1. The pure `core/`: `play()`, the lifecycle protocol, `CommandSource` (both directions), and the
   port interfaces — fully unit-tested with **fake/in-memory adapters**, no vendor deps.
1. One real adapter per essential port for the **web-first generative path** (bias: Playwright for
   player/recorder/locator/action-recording; driver.js for cues), behind the firewall.
1. The **capture-mode** path producing the same Demo Document via the interception observer.
1. One `RenderTarget` adapter against the real `reelee` contract (frozen JSON projection).
1. Two runnable `examples/` (one generative, one capture) and a `README.md` quickstart.
1. Narration (`Transcriber`/`Synthesizer`) wired with at least the draft-tier impl (e.g. Web
   Speech / Piper) and the WebVTT export; hosted-TTS adapter stubbed behind the same port.

**Order:** schema → pure core + fakes (tests green) → one adapter per port → capture mode →
render hand-off → narration → examples. Keep the core green at every step; adapters must never be
required to run core tests.

-----

## 8. Guardrails (re-stated because they are the ones most easily violated)

- Do **not** let any vendor or ecosystem type cross into `core/` or `ports/`.
- Do **not** store absolute time in the SSOT.
- Do **not** build branching traversal, effects graphs, or compositing — reserve the seam, write a
  note, move on.
- Do **not** add a cue type beyond the proven five without a rule-of-three justification in
  `DECISIONS.md`.
- Do **not** embed a renderer; emit a validated artifact and hand off.
- Do **not** silently rewrite a target locator via self-healing; log a human-reviewable suggestion.
- Do read both reports before choosing dependencies; they carry licenses and limitations this
  brief only summarizes.
- Do exercise judgment: you can see the code we cannot. Deviate when warranted, and record it.