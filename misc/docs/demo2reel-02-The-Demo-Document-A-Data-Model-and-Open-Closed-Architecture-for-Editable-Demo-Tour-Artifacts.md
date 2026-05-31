# The Demo Document: A Data Model and Open-Closed Architecture for Editable Demo/Tour Artifacts

*By Thor Whalen*

## TL;DR

- **The right data model is a sectioned, declarative “Demo Document”: an ordered list of typed `Step` objects whose atomic unit is an *enriched command* (`{command:{id,params}, timing, cues[], narration}`), separated onto parallel **tracks** (commands, cues, narration, camera) over a **relative, anchor-based time model** — not absolute timestamps and not a re-invented video timeline.** One Zod schema is the single source of truth (SSOT) for both generative and capture modes; the renderer (Reelee / Remotion-style) consumes a frozen JSON projection of it as input props.
- **The right architecture is a tiny pure core — `play(demoDoc, executor, observers)` — with everything swappable via dependency injection.** Generative and capture modes are the *same* core with the driver inverted: in generative mode the executor drives and observers record; in capture mode the human drives and an interception observer emits the same command stream. New cue types, recorders, narrators, and export targets attach at the registry/middleware seams already used by the command layer.
- **The single biggest risk is the inner-platform effect: re-inventing a video editor inside the schema.** Apply YAGNI and the rule of three rigorously — ship the minimal command+cue+narration+section schema first; reserve (but do not build) branching, parallel cue choreography, and B-roll until three real use cases demand them. The line is: *model intent richly enough to re-render, and delegate pixels, compositing, and transitions entirely to the renderer.*

-----

## Key Findings

1. **Prior art splits cleanly into two paradigms, and you want the editorial one, not the replay one.** Interactive-demo tools (Arcade, Storylane, Supademo, Navattic) treat the **step** as the atomic, addressable, editable unit — a screen/screenshot or DOM-clone plus hotspots/callouts. Session-replay tools (rrweb, PostHog, Sentry Replay) treat a **timestamped event** (a numeric-typed DOM mutation or input) as the atom; these are an append-only *log*, optimized for capture fidelity, not for editing. Your system’s atom — a named, typed, schema-defined command — maps onto the *step* abstraction, not the event-log abstraction, and is *more* re-renderable than either because the command is semantic intent rather than a screenshot or a DOM consequence.
1. **An enriched-command atom is correct, but a single flat list is not.** Commands, visual cues, and narration have *different lifetimes and cardinalities*: one command may carry zero or several cues; a narration phrase may span several commands; a “beat” (a pure pause, a text card, a B-roll insert) has no command at all. The schema must therefore allow **non-command beats** and represent cues/narration/camera on **separate tracks** that reference the command timeline by anchor — exactly the multi-track separation OpenTimelineIO and WebVTT use.
1. **Relative, anchor-based timing is the key to editability.** If timing is absolute (every element stamped with an offset from t=0), trimming or re-timing one section forces a recompute of everything downstream. The fix, validated by OpenTimelineIO’s `RationalTime`/`TimeRange` model and EDL source/record timecodes, is to make each section/step carry its own *local* duration and let global time be *derived* by composition. Editing a section then only touches that section.
1. **Visual cues are a small, well-bounded enum in practice.** Across Arcade, Storylane, and Supademo the recurring cue vocabulary is: highlight ring, spotlight/dim-surround, hotspot, callout/tooltip (optionally with arrow), synthetic cursor move+click, zoom/pan, blur-for-redaction, and text card/modal. Each needs a *target reference* and *type-specific parameters*. The hard problem is keeping the target reference stable; the testing world’s answer (Playwright locators, self-healing selectors) is to store a **resilient, prioritized locator** (role+accessible-name first, then test-id, then CSS/XPath) plus fallbacks, not a brittle single CSS path.
1. **Narration should be modeled as timed, editable text that round-trips through STT and TTS** — the Descript model. Store the *text* as SSOT, with a link to an optional rendered audio asset and the voice/engine parameters; represent word- or phrase-level timing the way WebVTT cues and SSML `<mark>`/bookmark events do. This lets you edit text → regenerate audio, or transcribe audio → edit text, without losing sync.
1. **Zod is the right SSOT bridge because the command layer already uses it.** A Zod schema yields (a) a static TypeScript type via `z.infer`, (b) runtime validation via `.parse`/`.safeParse`, and (c) a JSON Schema for external tools — “define once, validate everywhere.” One schema serves generative and capture modes because both produce the *same* artifact; the only difference is *who fills it in*.
1. **The renderer hand-off should be a frozen JSON projection consumed as “input props.”** Remotion — the canonical React-based programmatic renderer, and a good proxy for Reelee — renders a video as a pure function of JSON input props plus a frame number. This is the precise boundary you want: your system owns the *representation* (the Demo Document), the renderer owns the *pixels*. The artifact is the documented contract between them.

-----

## Details

### A. The Annotation / Demo-Document Schema

#### A.1 How prior systems model the editable unit (comparison)

|System                     |Atomic editable unit                                                                                                   |Timeline model                                                                                   |Target reference                                                                                                  |Editability mechanism                                                                |
|---------------------------|-----------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------------------|------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------------------------|
|**Arcade**                 |A **step** (captured image or video) with hotspots, callouts, spotlights, chapters; supports branching and pan-and-zoom|Ordered steps; per-step; chapters group steps                                                    |Position/area on the captured image; hotspot can route to any step                                                |Duplicate/merge/add/delete steps; edit hotspot text; “Page Morph” edits captured text|
|**Storylane**              |A **step** = screenshot *or* DOM/HTML clone, plus guided tooltip/hotspot                                               |Ordered guided steps                                                                             |HTML demos: guide dragged onto a DOM element (snaps when highlighted green); screenshot demos: overlay coordinates|No-code editor; edit data in HTML clone; AI tooltip text                             |
|**Supademo**               |A **step** (screenshot/recording) with hotspot, zoom, annotations                                                      |Ordered steps; optional conditional branching                                                    |Hotspot position/area on screenshot                                                                               |Edit hotspot color/position/transparency; AI voiceover per step                      |
|**Navattic**               |A **step** built on a full **HTML/CSS capture** (pixel-perfect clone)                                                  |Ordered steps; storyboards                                                                       |Live DOM element in the cloned page                                                                               |Drag-and-drop editor; edit cloned DOM                                                |
|**rrweb**                  |A **timestamped event** (numeric `type`; full vs. incremental snapshot; sources: Mutation, MouseMove, Input, Scroll, …)|Absolute `timestamp` per event; incremental-snapshot chain from a full snapshot                  |DOM node `id` from the mirror (serialized DOM tree)                                                               |Not designed for editing; events replay against the initial snapshot                 |
|**PostHog / Sentry Replay**|rrweb events batched into `$snapshot_items` (newline-delimited `[windowId, event]`)                                    |Absolute timestamps; session-scoped                                                              |rrweb node ids                                                                                                    |Analysis/search, not authoring                                                       |
|**Playwright trace**       |An **action** (every API call: click/fill/expect) with before/after DOM snapshots, screenshots, timing                 |Action log with per-action time range; `.zip` archive                                            |Resilient **locator** (role+name, test-id, CSS/XPath)                                                             |Inspect/replay; codegen emits editable code                                          |
|**Playwright codegen**     |A generated **action statement** (`getByRole(...).click()`)                                                            |Sequential statements                                                                            |Prioritized resilient locator                                                                                     |Edit generated source code                                                           |
|**OpenTimelineIO**         |A **Composable** (Clip, Gap, Transition) inside Track/Stack                                                            |`RationalTime`/`TimeRange`; `source_range`, `available_range`, `trimmed_range`; relative/composed|Clip → `ExternalReference` (media `target_url`)                                                                   |Programmatic mutable-sequence API; markers; nesting                                  |
|**Descript**               |A **word** in the transcript, linked to media                                                                          |Transcript-aligned; non-destructive                                                              |Word ↔ media span mapping                                                                                         |Edit text → media updates; delete words; regenerate                                  |
|**WebVTT / SRT**           |A **cue** (id + start/end + payload, optional settings)                                                                |Per-cue start/end timestamps; cues may overlap (except chapters)                                 |N/A (screen position via cue settings)                                                                            |Plain-text edit; diffable                                                            |

**Reading of the table.** The editorial tools converge on the *step* as the editable unit; the observability tools converge on the *timestamped event*. Your command stream sits semantically above rrweb events (a command is intent; a mutation is consequence) and is a near-perfect match for the *step* abstraction — but enriched with the structured `{commandId, params}` you already have, which is *better* than a screenshot because it is re-executable.

#### A.2 The enriched-command atom — proposal and critique

The natural atom is:

```
Step = {
  command?: { id, params },                       // existing typed command; OPTIONAL (beats have none)
  timing:   { offset?, duration, holdAfter? },    // LOCAL/relative time
  cues?:    Cue[],                                 // zero or more, on the cue track
  narration?: NarrationRef                         // links into the narration track
}
```

A demo is an **ordered, sectioned list** of these. This is right, but a flat list of enriched commands is *missing* four things, each of which the literature shows you eventually need:

- **Non-command beats.** A pure narration pause, a title/text card, or a B-roll insert has no command. Model `Step.command` as optional and add a `kind` discriminator (`command` | `beat`). WebVTT’s NOTE/chapter cues and OTIO’s `Gap`/`GeneratorReference` are the precedents.
- **Parallel / overlapping cues.** A spotlight that persists *while* the cursor moves and a callout fades in is three cues with overlapping lifetimes. A single `cues[]` attached to one command cannot express overlap that crosses command boundaries. Put cues on their **own track** anchored to step boundaries (like WebVTT allowing overlapping cue timings, and OTIO stacking tracks).
- **Narration that spans commands.** One spoken sentence often covers several UI actions. Narration must be a **track of timed-text segments** anchored to step ranges, not a field crammed into one command.
- **Camera/viewport as a first-class track.** Zoom/pan is not a per-element decoration; it is a continuous *camera state over time*, exactly like a camera track in an NLE. Model it as its own track so a pan can outlast the command that triggered it.

**Branching** is the one item to *defer* (see Pitfalls). Arcade and Supademo support it, but it is the feature most likely to drag you into the inner-platform trap.

#### A.3 Time model — relative, anchored, composed

Use **relative timing with derived absolutes**, mirroring OpenTimelineIO and EDLs:

- Each `Step` and `Section` carries a **local** `duration` (and optional `holdAfter`); it does *not* store an absolute start.
- Global time is **computed by composition** (sum of preceding durations), the way OTIO derives a clip’s `range_in_parent` from its position and the way an EDL’s record-in/record-out are conformed from source ranges.
- Cues and narration anchor to a **(stepId, localOffset)** pair, not to absolute t. Trimming a section changes only that section’s contribution; everything downstream shifts automatically because nothing downstream stored an absolute number.
- Represent durations as a rational/typed quantity (OTIO’s `RationalTime` is `value/rate`) or simply milliseconds; avoid frame counts in the SSOT and let the renderer convert to frames (Remotion uses `fps`+`durationInFrames`).

**Is OpenTimelineIO usable as the interchange format?** As *inspiration*, strongly yes — its Timeline→Stack→Track→(Clip|Gap|Transition) model, its `metadata` dict on every object, and its relative time math are exactly the right shapes. As the *literal on-disk SSOT*, no: OTIO models *media on tracks for compositing*, whereas your SSOT models *intent (commands) + annotations*. Adopt OTIO’s structure and time algebra; keep your own command-centric schema. You can always emit OTIO as one *export target* for NLE round-trips.

#### A.4 Visual-cue taxonomy

|Cue type                |Required parameters                              |Target reference                 |
|------------------------|-------------------------------------------------|---------------------------------|
|Highlight ring          |color, thickness, padding, shape                 |element locator / bbox           |
|Spotlight / dim-surround|overlay opacity/color, cutout shape, feather     |element locator / area bbox      |
|Hotspot                 |pulse style, size, click-to-advance/route        |element locator / coordinate     |
|Callout / tooltip       |text, placement, arrow direction, dimensions     |anchor locator + offset          |
|Synthetic cursor        |from/to coordinates, easing, duration, click flag|start/end coordinate or locator  |
|Zoom / pan (camera)     |focus rect, zoom factor, easing, hold            |area bbox (lives on camera track)|
|Blur / redaction        |region, blur radius                              |bbox (coordinate-based by design)|
|Arrow / annotation      |from/to, style                                   |two locators/coordinates         |
|Text card / modal       |text, layout, enter/exit                         |none (full-frame beat)           |

**Target referencing and stability.** Store a **resilient, prioritized reference**, learning from Playwright (which “figures out the best locator, prioritizing role, text and test id locators”  and refines it until it uniquely identifies the element) and from self-healing-locator practice (keep a *list* of candidate locators — role/aria, test-id, text, CSS, XPath, bbox, screenshot fingerprint — and fall back in ranked order). Concretely, a cue target should be:

```
Target = {
  primary:  Locator,           // e.g., role + accessibleName
  fallbacks: Locator[],        // test-id, text, CSS, xpath
  bbox?:     Rect,             // last-resort geometry captured at record time
  scrollAnchor?: {...}         // to re-find after scroll-position changes
}
```

This directly addresses scroll-position adjustment after capture (store the scroll anchor) and UI drift (fall back down the locator list, optionally with a self-healing pass that *logs a suggested fix for human review* rather than silently mutating the SSOT). Treat self-healing efficacy claims with appropriate skepticism: QA Wolf’s January 2026 analysis reports that “DOM changes and brittle selectors account for only about 28% of test failures, while over 70% come from timing issues, test data problems, runtime errors, and rendering failures”  — i.e., a healthy locator strategy solves only part of the stability problem, so favor robust anchoring over clever auto-repair.

#### A.5 Narration model

Adopt the **Descript principle — the transcript is the editable surface, the media follows the text** (“when you edit your transcript, Descript automatically updates the underlying media — no timeline required”)  — combined with WebVTT/SSML structures:

```
NarrationSegment = {
  id, text,                                     // SSOT: the words (diffable, editable)
  anchor: { stepId, localOffset, duration },    // when it plays, relative
  audioRef?: AssetRef,                          // optional rendered audio (regenerable)
  tts?: { engine, voice, rate, ssml? },         // synthesis parameters
  wordTimings?: [{ word, t }]                   // optional, from STT or TTS marks
}
```

- **Round-tripping:** STT (capture mode: transcribe the human’s spoken narration) populates `text` + `wordTimings`; editing `text` invalidates `audioRef` and triggers TTS regeneration. This is the Descript loop (“edit the transcript to edit the audio”), made explicit in data.
- **Timed-text precedent:** A WebVTT cue is `{id, start, end, payload}` with optional positioning — your `NarrationSegment` is a WebVTT cue with an anchor instead of an absolute time, so you can export `.vtt`/`.srt` captions for free.
- **Word-level marks:** TTS engines emit timing via SSML `<mark>`/bookmark events (Azure’s `BookmarkReached`,  Google/Amazon `<mark>` timepoints). Persist these as `wordTimings` so karaoke-style highlight cues and tight re-timing are possible.

#### A.6 Serialization & SSOT

- **JSON is the wire format; a Zod schema is the source.** The command layer already uses Zod/JSON Schema; reuse that bridge. A single Zod schema gives you the TypeScript type (`z.infer`), runtime validation (`.parse`/`.safeParse`), and a generated JSON Schema for external/renderer tooling — keeping types, validation, and docs from drifting apart.
- **Diffable & version-controllable:** plain JSON with stable element ids and *relative* timing diffs cleanly (a trimmed section is a local diff). Avoid absolute timestamps precisely because they make every edit a whole-file diff.
- **One model, two modes:** the artifact is identical for generative and capture; only the *producer* differs. Generative authoring writes the Demo Document directly; capture mode synthesizes the same Demo Document from the intercepted command stream + recorded audio + captured targets. Validating both through the *same* Zod schema guarantees they are interchangeable downstream.

### B. The Extensible Architecture

#### B.1 Minimal core: the player + observer protocol

The core is one pure, higher-order function — declarative in, effects injected:

```
play(
  demoDoc: DemoDocument,
  executor: (command) => Promise<Result>,   // the EXISTING command-dispatch layer
  observers: Observer[]                       // recorder, overlay, pacer, narrator, logger
) => Promise<Outcome>
```

The core only knows how to **walk the document and emit lifecycle events**; it never renders, records, or speaks. Observers subscribe to a fixed lifecycle protocol:

- `onDemoStart(doc)` / `onDemoEnd(outcome)`
- `onSectionEnter(section)` / `onSectionExit(section)`
- `onStepEnter(step)` → `beforeCommand(cmd)` → `afterCommand(cmd,result)` | `onCommandError(cmd,err)` → `onStepExit(step)`
- `onCueBegin(cue)` / `onCueEnd(cue)`
- `onNarration(segment)`
- `onBeat(beat)` (non-command)

This is the **observer/middleware pattern** the command layer already uses — observers are pure subscribers, composed as a list, each independent (composition over inheritance). The recorder is just an observer that writes video; the overlay renderer is an observer that draws cues; the narrator is an observer that plays/synthesizes audio; the pacer is an observer that injects pauses. All are **injected dependencies** and therefore swappable.

#### B.2 Generative and capture as one core with the driver inverted

The two modes are **configurations, not codebases**:

- **Generative mode:** the **executor drives**. `play` reads each `Step.command` and calls `executor(command)`; observers record video, draw cues, and synthesize narration as the lifecycle fires. The document is the input.
- **Capture mode:** the **human drives**. The same `play` lifecycle runs, but instead of pulling commands from a document, an **interception observer** taps the live command stream (the command-dispatch layer already names and types every operation) and *emits* `Step`s into a fresh Demo Document; other observers record video and transcribe audio. The document is the output.

The pattern that “cleanly inverts the driver while keeping the observer protocol identical” is **inversion of control via a pluggable source**: abstract the command sequence behind a `CommandSource` (a pull-iterator for generative; a push-stream adapter for capture). The lifecycle protocol — and therefore every observer — is byte-for-byte identical in both modes. This is the strangler-fig/facade insight applied locally: a thin facade over “where commands come from” lets one engine serve both directions without touching the dispatch layer (open-closed).

#### B.3 Plugin boundaries (the open-closed seams)

Map each axis of extension to a known pattern, reusing the command layer’s existing registry+middleware where possible:

|Extension axis                                       |Seam / pattern                                                                                   |How a new one is added without touching the core                                                              |
|-----------------------------------------------------|-------------------------------------------------------------------------------------------------|--------------------------------------------------------------------------------------------------------------|
|New **cue type**                                     |**Registry of cue handlers** (`cueType → {validate, render}`); cue payload typed by a Zod variant|Register a handler + schema variant; the overlay observer dispatches by `cue.type` (visitor over the timeline)|
|New **recorder backend**                             |**Strategy**, injected as an observer                                                            |Implement the `Recorder` interface; inject it. Core unchanged                                                 |
|New **narration synthesizer**                        |**Strategy** behind a `Narrator` port                                                            |Implement `synthesize(segment)→audioRef`; inject it                                                           |
|New **export target** (Reelee, OTIO, WebVTT, GIF)    |**Registry of exporters** + **visitor** over the document                                        |Register `export(demoDoc)→artifact`; walk the typed tree                                                      |
|New **command**                                      |Already handled by the **existing command registry**                                             |No demo-system change; the new command flows through automatically                                            |
|Cross-cutting concerns (timing, redaction, analytics)|**Middleware/pipeline** around `executor` and around observers                                   |Wrap, don’t modify                                                                                            |

Because cues and observers reuse the command layer’s **registry + middleware** mechanisms, the demo system introduces *no new extension paradigm* — it inherits the one the team already knows (progressive disclosure: simple by default, pluggable when needed).

#### B.4 The renderer hand-off contract (Reelee, Remotion, etc.)

**The stable, documented artifact the renderer consumes is the frozen JSON projection of the Demo Document** — validated against the published Zod/JSON Schema, with all relative timings resolved into a render-ready form (or left relative, with the renderer doing the composition). The boundary is: **your system owns representation; the renderer owns pixels.**

Remotion is the concrete proof that this boundary works. In Remotion, “input props are data that can be passed to a render in order to parametrize the video,”  they “must be an object and serializable to JSON,”  and they are “passed to the `component` of your `<Composition>` directly.”  On the CLI the hand-off is literally a JSON string or file: `--props='{...}'` “must be either valid JSON or a path to a file that contains valid JSON.”  The render is data-driven and deterministic: “a video is a function of images over time,”  defined by `width`, `height`, `fps`, and `durationInFrames`,  with `<Sequence>` time-shifting children by frame `from` (“a `<Sequence>` is a built-in component that manipulates the time for its children”).  The same `inputProps` drive both the interactive Studio and headless `renderMedia()`/Lambda rendering — i.e., one JSON data model renders to identical pixels anywhere. Remotion even uses **Zod schemas attached via a `schema` prop** to type and visually edit those props (“you may use Zod to define a schema for your props… if you want to edit the props visually in the Remotion Studio”),  and a `calculateMetadata()` stage to transform incoming data and derive duration — mirroring exactly the SSOT-plus-transform pipeline proposed here (external JSON → optional transform → final props handed to the renderer).

**Candidate / inspirational hand-off formats:**

- **Your Demo Document JSON (recommended primary):** semantically richest; carries commands, cues, narration, and intent the renderer can lay out freely.
- **OpenTimelineIO (export target):** for round-tripping into professional NLEs; gives you tracks/clips/gaps/transitions and relative time math for free.
- **WebVTT/SRT (export target):** caption sidecar generated from the narration track at zero extra cost.
- **rrweb event JSON (reference only):** instructive for *capture fidelity* but the wrong SSOT — it is a replay log, not an editable score.

A clean rule: **the renderer should be able to ignore anything it does not understand** (the way an OTIO player “may simply ignore transitions”  it cannot render, and “the overall length of the timeline will not be affected”)  and still produce a coherent video. That keeps the contract forward-compatible.

### C. Pitfalls

- **Inner-platform effect — the dominant risk.** As Alex Papadimoulis defined it on The Daily WTF in 2006, “the Inner-Platform Effect is a result of designing a system to be so customizable that it ends becoming a poor replica of the platform it was designed with. This ‘customization’ of this dynamic inner-platform becomes so complicated that only a programmer (and not the end user) is able to modify it.”  Here that platform is a *video editor / NLE*. If the schema grows keyframe interpolation curves, compositing blend modes, nested transitions, and a generic effects graph, you will have built a worse Premiere inside JSON — requiring a programmer, not an author, to edit it. **Mitigation:** the SSOT models *intent and annotation*; all compositing, easing curves, and transition rendering live in the renderer. The schema says “spotlight this element while narrating X”; it does *not* say “lerp the alpha of layer 3 from 0.2 to 0.8 over 12 frames.”
- **Premature generalization of cue/branch types (YAGNI + rule of three).** As Ron Jeffries, the XP co-founder who coined YAGNI, put it: “Always implement things when you actually need them, never when you just foresee that you need them.”  And on abstraction timing, Martin Fowler’s *Refactoring* (1999) attributes the rule of three to Don Roberts: “The first time you do something, you just do it. The second time you do something similar, you wince at the duplication, but you do the duplicate thing anyway. The third time you do something similar, you refactor.”  Concretely: ship the ~5 cue types that Arcade/Storylane/Supademo actually use; do **not** build a generic cue-effect DSL on day one.
- **The wrong abstraction for “step.”** In “The Wrong Abstraction” (2016), drawn from her RailsConf 2014 talk, Sandi Metz warns that “duplication is far cheaper than the wrong abstraction,”  and “when the abstraction is wrong, the fastest way forward is back. This is not retreat, it’s advance in a better direction.”  If you force commands, beats, cues, and narration into one over-parameterized `Step` type bristling with optional flags and conditionals, you’ve created the wrong abstraction. Prefer a small **discriminated union** (`CommandStep | Beat`) with cues/narration on their own tracks; let the shapes stay distinct until a genuine third case proves a unifying abstraction.
- **Absolute-time coupling.** Storing absolute timestamps (the rrweb/replay model) couples every edit to a global recompute and makes diffs enormous. Use relative/anchored time from the start.
- **Brittle target references.** A single CSS selector captured at record time will rot (Playwright’s own guidance: “your DOM can easily change so having your tests depend on your DOM structure can lead to failing tests”).  Store a prioritized locator list + bbox + scroll anchor, and treat self-healing as a *suggestion to a human*, never a silent rewrite of the SSOT.

-----

## Recommendations

**Stage 1 — Minimal viable schema (build now).** Ship the smallest SSOT that can re-render:

- `DemoDocument { id, meta, sections: Section[] }`
- `Section { id, title?, steps: Step[] }`
- `Step` as a discriminated union: `CommandStep { command:{id,params}, timing:{duration,holdAfter?}, cueRefs?, narrationRef? }` and `Beat { kind, timing, ... }`
- Three tracks referenced by anchor: **cues**, **narration**, **camera** — even if camera starts with only “zoom/pan.”
- Cue types limited to the proven five: highlight, spotlight, hotspot, callout, cursor.
- `NarrationSegment` with `text` as SSOT + optional `audioRef`/`tts`.
- One **Zod schema** as SSOT; emit JSON Schema for the renderer.
- The core `play(demoDoc, executor, observers)` with the lifecycle protocol of B.1, and a `CommandSource` facade so capture mode reuses it.
- One recorder observer, one overlay observer, one narrator observer — all injected.
- One exporter: the frozen JSON projection for Reelee/Remotion-style rendering.

**Stage 2 — Earn the extensions (build when a metric/threshold is hit).**

- Add a new cue type **only after the third real request** for it (rule of three). Until then, compose existing cues.
- Add **OTIO and WebVTT exporters** when an actual NLE round-trip or caption requirement appears.
- Add **word-level `wordTimings`** when karaoke-style highlighting or sub-second re-timing is genuinely needed (wire SSML marks then, not before).
- Add **self-healing locators** when target drift is observed in real captures; ship it as human-reviewed suggestions, not silent rewrites.

**Stage 3 — Defer until proven necessary (reserve seams, write no code).**

- **Branching/conditional paths.** Reserve a `next: stepId | Branch` seam in the schema’s type, but do not implement traversal until ≥3 demos need non-linear flow. This is the single feature most likely to trigger the inner-platform effect.
- **Parallel cue choreography across sections**, **B-roll/PiP compositing**, **effects graphs.** Keep these in the renderer’s domain.

**Thresholds that change the plan.** Build branching when ≥3 stakeholders have a concrete non-linear demo; build a generic cue-effect plugin when ≥3 distinct cue types share ≥80% of their handler code (the genuine rule-of-three signal); adopt OTIO as a *first-class* internal model only if you find yourself re-implementing track/clip/gap math more than once.

-----

## Caveats

- **Reelee could not be positively identified** from public sources during research; multiple similarly named tools exist (e.g., Rendy, Rendley, Remotion, Renderforest). I have therefore treated “Reelee” as *a* downstream programmatic renderer and used **Remotion** as the concrete, well-documented proxy for the data→pixels hand-off. If Reelee’s actual input contract differs, the *boundary principle* (system owns representation, renderer owns pixels; hand off validated JSON) still holds; only the field-mapping adapter changes.
- **Vendor descriptions of interactive-demo tools come largely from the vendors themselves** (Arcade, Storylane, Supademo blogs/docs) and from comparison sites that may be commercially motivated; the *structural* facts used here (step as unit, hotspots/callouts/spotlights, branching, screenshot-vs-HTML capture) are consistent across independent sources and are the load-bearing claims.
- **Self-healing-locator efficacy figures** (the “~28% of failures” datapoint) originate from a vendor (QA Wolf) and should be read as directional, not authoritative.
- The proposed schema is an **architecture recommendation, not a tested implementation**; the rule-of-three and YAGNI guidance explicitly assumes you will discover real requirements that adjust the details. The whole point is to keep the core small enough that those adjustments stay cheap.

-----

## References

1. [rrweb — Dive Into Events (event JSON, incremental snapshots)](https://github.com/rrweb-io/rrweb/blob/master/docs/recipes/dive-into-event.md)
1. [rrweb — repository overview (record/replay, snapshot)](https://github.com/rrweb-io/rrweb)
1. [What is rrweb? — event structure and numeric types](https://slyracoon23.github.io/blog/posts/2025-03-14_what_is_rrweb.html)
1. [PostHog — Session replay architecture](https://posthog.com/handbook/engineering/session-replay/session-replay-architecture)
1. [OpenTimelineIO — Timeline Structure (Tracks, Clips, Gaps, Transitions)](https://opentimelineio.readthedocs.io/en/latest/tutorials/otio-timeline-structure.html)
1. [OpenTimelineIO — Time Ranges (RationalTime, source/trimmed/available range)](https://opentimelineio.readthedocs.io/en/latest/tutorials/time-ranges.html)
1. [OpenTimelineIO — Architecture (schema, opentime, adapters)](https://opentimelineio.readthedocs.io/en/latest/tutorials/architecture.html)
1. [Playwright — Trace Viewer (action log, DOM snapshots)](https://playwright.dev/docs/trace-viewer)
1. [Playwright — Tracing API](https://playwright.dev/docs/api/class-tracing)
1. [Playwright — Test generator (codegen, locator prioritization)](https://playwright.dev/docs/codegen)
1. [Playwright — Locators (role/name, test-id, CSS/XPath)](https://playwright.dev/docs/locators)
1. [Playwright — Best Practices (resilient locators)](https://playwright.dev/docs/best-practices)
1. [Arcade — Hotspots, Callouts & Spotlights](https://docs.arcade.software/kb/build/interactive-demo/edit/hotspots-callouts-and-spotlights)
1. [Arcade — Interactive Demo Software (pan & zoom, chapters)](https://www.arcade.software/product/interactive-demo)
1. [Storylane — Adding and Editing Guided Steps](https://docs.storylane.io/editing-demos/adding-and-editing-guided-steps)
1. [Storylane vs Navattic (capture method: screenshot vs HTML)](https://www.saltfish.ai/blog/storylane-vs-navattic)
1. [Navattic vs Storylane vs Supademo (branching, capture)](https://supademo.com/blog/navattic-vs-storylane-vs-supademo)
1. [Storylane vs Supademo (hotspot config, conditional branching)](https://www.floik.com/blog/storylane-vs-supademo)
1. [Descript — Edit like a doc (transcript-driven editing)](https://help.descript.com/hc/en-us/articles/15726742913933-Edit-like-a-doc)
1. [Descript — Automatic transcription](https://help.descript.com/hc/en-us/articles/10249424286477-Automatic-transcription)
1. [WebVTT — MDN (cue structure and timings)](https://developer.mozilla.org/en-US/docs/Web/API/WebVTT_API/Web_Video_Text_Tracks_Format)
1. [WebVTT — W3C specification](https://www.w3.org/TR/webvtt1/)
1. [Edit Decision List — Wikipedia (CMX3600, source/record timecode)](https://en.wikipedia.org/wiki/Edit_decision_list)
1. [Guide to EDL Management — edlmax.com](https://edlmax.com/EdlMaxHelp/Edl/maxguide.html)
1. [SSML document structure and events — Azure (bookmark / BookmarkReached)](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/speech-synthesis-markup-structure)
1. [SSML — Google Cloud Text-to-Speech (mark / timepoints)](https://docs.cloud.google.com/text-to-speech/docs/ssml)
1. [Zod — TypeScript-first schema validation (z.infer, parse/safeParse)](https://github.com/colinhacks/zod)
1. [Treat Zod Schemas as Single Source of Truth — egghead.io](https://egghead.io/treat-zod-schemas-as-single-source-of-truth~8fli2)
1. [Remotion — Passing props / input props (–props, JSON-serializable)](https://www.remotion.dev/docs/passing-props)
1. [Remotion — Parameterized videos](https://www.remotion.dev/docs/parameterized-rendering)
1. [Remotion — The Fundamentals (video as a function of images over time; fps, durationInFrames)](https://www.remotion.dev/docs/the-fundamentals)
1. [Remotion — Sequence (time-shifting children)](https://www.remotion.dev/docs/sequence)
1. [Remotion — Schemas (Zod schema prop, visual editing)](https://www.remotion.dev/docs/schemas)
1. [Remotion — calculateMetadata() and props resolution](https://www.remotion.dev/docs/calculate-metadata)
1. [Remotion — Server-side rendering (renderMedia, inputProps)](https://www.remotion.dev/docs/ssr-node)
1. [The Inner-Platform Effect — The Daily WTF (Alex Papadimoulis, 2006)](https://thedailywtf.com/articles/The_Inner-Platform_Effect)
1. [Inner-platform effect — Wikipedia](https://en.wikipedia.org/wiki/Inner-platform_effect)
1. [The Wrong Abstraction — Sandi Metz](https://sandimetz.com/blog/2016/1/20/the-wrong-abstraction)
1. [Rule of three (computer programming) — Wikipedia](https://en.wikipedia.org/wiki/Rule_of_three_(computer_programming))
1. [Premature Generalization — deparkes](https://deparkes.co.uk/2017/11/03/premature-generalization/)
1. [Refactoring and the Rule of Three (YAGNI, AHA, Jeffries)](https://incusdata.com/blog/refactoring-the-rule-of-three)
1. [Strangler Fig pattern — Wikipedia (Fowler)](https://en.wikipedia.org/wiki/Strangler_fig_pattern)
1. [Strangler Fig Design Pattern (facade) — DevIQ](https://deviq.com/design-patterns/strangler-fig-pattern/)
1. [Dependency Injection — DevIQ](https://deviq.com/practices/dependency-injection/)
1. [The 6 Types of AI Self-Healing in Test Automation — QA Wolf](https://www.qawolf.com/blog/self-healing-test-automation-types)
1. [Self-Healing Test Automation — Tricentis (element fingerprints, test-ids)](https://www.tricentis.com/learn/self-healing-test-automation)