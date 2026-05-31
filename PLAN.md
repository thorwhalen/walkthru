# walkthru — Implementation Plan

> Deliverable 1 of the build brief (`misc/docs/WALKTHRU-AGENT-BRIEF.md`). Written **after**
> reading both reports *and* inspecting the actual ecosystem code (`acture`, `zodal`,
> `reelee`, `reelee-web`, `dol`). Deviations from the brief are recorded in
> [`DECISIONS.md`](./DECISIONS.md); the running development journal lives in this repo's
> **enhancement issues**.

---

## 0. What inspection changed

The brief stated several conclusions as "decided" but explicitly delegated final judgment to
whoever could see the ecosystem code. Three of those conclusions move:

| Brief said | Ecosystem reality | Consequence |
|---|---|---|
| Command layer is "an existing command-dispatch architecture" (unnamed) | It is **`acture`** (TS/React, Apache-2.0). It already ships `recordSequence()` (capture) and `replaySequence()` (replay) over `registry.dispatch`. | walkthru is a *thin consumer* of acture, not a new engine. `play()` ≈ `replaySequence(registry, seq, {onStep})`; capture ≈ wrap `registry.dispatch`. |
| Zod is the presumptive SSOT; author the schema in Zod/`zodal` | The federation authors schemas in **Pydantic (Python)** and **codegens Zod** from the exported JSON Schema (`reelee` → `reelee-web`). | SSOT authored **Python-first** (Pydantic v2); Zod is codegened. Reverses the brief's bias — see [`DECISIONS.md`](./DECISIONS.md) §D1. |
| Renderer hand-off ≈ Remotion "input props" (proxy for `reelee`) | `reelee` is a **MoviePy/ffmpeg Ken Burns** renderer. Input contract = a `reelee.Project` graph → ordered `list[PanelView]` + `render_kenburns_video(...)` kwargs. **Not Remotion.** | First `RenderTarget` adapter maps the Demo Document → reelee's `PanelView`/`render_kenburns_video` contract. Remotion stays a *secondary, external* adapter. See §6. |

Everything else in the brief (tiny pure core, DI ports, relative anchor-based time, the five
cue types, reserve-don't-build branching, the core/adapter firewall) survives inspection
unchanged and is adopted.

---

## 1. Schema technology & SSOT

**Author the Demo Document once, in Python Pydantic v2, as the SSOT.** Emit JSON Schema from
it; codegen Zod v4 types for the TS side. JSON is the wire format.

Rationale (full version in [`DECISIONS.md`](./DECISIONS.md) §D1):

- It is the **established federation pattern**: `reelee` defines Pydantic body schemas
  (registered via `lacing.register_body_schema`), exports JSON Schema (`reelee
  export-schemas`), and `reelee-web` codegens its Zod types from that export. Matching this
  means walkthru's Demo Document can register as a `lacing` body schema *for free* (optional
  ecosystem adapter) and round-trips losslessly with the renderer side.
- Pydantic v2 gives validation **and** JSON-Schema emission in one dependency — exactly the
  "define once, validate everywhere" the brief wants, just on the Python side of the bridge.
- **Ecosystem-independence is preserved.** Pydantic is a permissive third-party dep, *not* an
  ecosystem package. `core/` imports only Pydantic; the `lacing`/`acture`/`reelee` hooks live
  behind the firewall in `ecosystem/`.

**Round-trip strategy.** `schema/` holds (a) the JSON Schema emitted from the Pydantic SSOT,
(b) the codegened Zod, and (c) fixtures. A CI test serializes a `DemoDocument` in Python,
validates it against the Zod schema in TS, and round-trips it back to Python — proving the
two sides are interchangeable.

> Constraint inherited from `acture`: command `params` must stay within the
> JSON-Schema-representable subset (no `z.transform/date/bigint/set/map`). Our Pydantic models
> honor the same subset so the codegened Zod is faithful.

---

## 2. Repository layout

Follows **wads current defaults** on the Python side: the package sits at the repo root — the
`name/name/` form — not under `src/` and not under a `py/` subdir. The repo root *is*
`walkthru/`, so the Python package is `walkthru/walkthru/`. The TypeScript side lives in a
sibling `ts/` subdir as a single npm package.

```
walkthru/                        # repo root
  README.md  PLAN.md  DECISIONS.md  LICENSE
  .gitignore  .gitattributes  .editorconfig        # wads defaults
  pyproject.toml                 # hatchling, py>=3.10, MIT, ruff D100, [tool.wads.ci.*]
  walkthru/                      # PyPI "walkthru" — package at root (wads name/name form)
    __init__.py
    core/                        # PURE: play(), lifecycle, CommandSource, schema (Pydantic SSOT)
    ports/                       # Protocols: CommandPlayer, Recorder, ElementLocator, CueRenderer,
                                 #            ActionRecorder, Transcriber, Synthesizer, RenderTarget
    adapters/                    # OPTIONAL impls, isolated: playwright/, obs/, whisperx/, piper/
    ecosystem/                   # OPTIONAL: reelee/, acture/, lacing/  (schema registration)
  tests/                         # Python tests (smoke now; core tests at MVP Stage 1)
  ts/                            # npm "acture-walkthru" — single TS package (scaffolded later)
    package.json                 #   generated by the wads `ts` profile once i2mint/wads#39 lands
    src/{core,ports,adapters,ecosystem}/
    tests/
  schema/                        # JSON Schema (emitted from Pydantic) + codegened Zod + fixtures
  examples/                      # one generative web demo + one capture-mode demo
  misc/docs/                     # the brief + the two reports (intent SSOT)
  .github/workflows/
    ci.yml                       # Python uv-CI stub (now) → i2mint/wads reusable workflow
    npm-ci.yml                   # frontend CI — DEFERRED until the wads `ts` profile (issue #39)
```

> **Frontend CI is intentionally deferred.** Per coordination with **i2mint/wads#39**
> (generalize the frontend overlay into a js/ts language-profile registry), walkthru ships the
> **Python side on wads current defaults now** and adopts the resulting `ts` profile for its
> `ts/` subdir + `npm-ci.yml` once that issue lands — so the two work streams don't collide.
> See `DECISIONS.md` §D6. The TS side is a **single package** (`acture-walkthru`); the
> core/adapter firewall is enforced *within* it via subpath exports + an import-boundary lint
> + optional peer deps, so we do not need a multi-package monorepo for MVP.

**Firewall (mandatory, CI-enforced):** `core/` and `ports/` import nothing from `adapters/`
or `ecosystem/`. Adapters depend on ports, never the reverse. A CI check imports the core
with **no optional deps installed** and asserts it loads and its tests pass.

**Language split is intentional, not redundant:**

- **TS `acture-walkthru`** is where the *live* action is — capture taps `acture`'s
  `registry.dispatch`; generative play replays through the same registry. Browser cues
  (driver.js), synthetic cursor (Motion/FLIP), and draft narration (Web Speech / Kokoro.js)
  live here.
- **Python `walkthru`** owns the **SSOT authoring** (Pydantic), JSON-Schema emission, the
  **render hand-off** to `reelee`, and heavy narration (WhisperX / Piper). A Python `play()`
  mirror drives Playwright-Python for headless generative runs.
- The **JSON Demo Document** is the only thing that crosses between them.

---

## 3. The MVP cut

### 3.1 Schema fields (Stage 1 — build now)

- `DemoDocument { id, meta, sections: Section[], tracks: { cues, narration, camera } }`
- `Section { id, title?, steps: Step[] }`
- `Step` = discriminated union on `kind`:
  - `CommandStep { kind:"command", command:{id, params}, timing:{duration, holdAfter?},
    cueRefs?, narrationRef? }` — `command` mirrors acture's `SequenceStep {commandId, params}`.
  - `Beat { kind:"beat", beatKind:"pause"|"textCard"|"broll", timing, … }`
- **Three tracks referenced by anchor** (`{stepId, localOffset}`), never crammed into a step:
  `cues`, `narration`, `camera`.
- **Time is relative.** Each Step/Section carries a local `duration` (+ optional `holdAfter`),
  expressed in **milliseconds**. Global time is derived by composition. **No absolute
  timestamps in the SSOT.** The renderer converts ms → frames.
- `NarrationSegment { id, text, anchor:{stepId, localOffset, duration}, audioRef?, tts?,
  wordTimings? }` — `text` is the editable SSOT; editing it invalidates `audioRef`.
- **Reserved as a type-level seam only (no traversal code):** `next: stepId | Branch`.

### 3.2 The five cue types (MVP — no more without rule-of-three)

`highlight` (ring), `spotlight` (dim-surround), `hotspot`, `callout` (tooltip),
`cursor` (synthetic). Each is a typed variant carrying a **resilient target reference**:

```
Target = { primary: Locator, fallbacks: Locator[], bbox?: Rect, scrollAnchor?: {...} }
```

Re-resolve by `primary`, fall back down the list. Any self-healing is a **logged suggestion
for human review**, never a silent SSOT rewrite.

### 3.3 Ports (the seven facades — no vendor type crosses them)

`CommandPlayer.play(command)→result` · `Recorder.start()/stop()→media_ref` ·
`ActionRecorder.record()→command_stream` · `ElementLocator.bounds(target)→rect` ·
`CueRenderer.show(cue, rect)` · `Transcriber.transcribe(audio)→timed_words` ·
`Synthesizer.say(text)→audio` · `RenderTarget.export(artifact)→video`.

### 3.4 First adapter per port (web-first, bias confirmed)

| Port | First real adapter | Notes |
|---|---|---|
| `CommandPlayer` | **`acture` registry** (`dispatch`) | The executor *is* `acture`. For non-acture web, Playwright `page`. |
| `ActionRecorder` | **`acture` `recordSequence` / dispatch-wrap** | Capture mode (§5). |
| `Recorder` | **Playwright `screencast`** | Swap to OBS/ffmpeg for hero quality with zero core change. |
| `ElementLocator` | **Playwright `boundingBox()`** | |
| `CueRenderer` | **driver.js** (spotlight/highlight) + DOM callouts | Avoid intro.js (AGPL). |
| `Transcriber` | **WhisperX** (draft: Web Speech) | |
| `Synthesizer` | **Piper** (MIT) (draft: Web Speech / Kokoro.js) | Hosted TTS stubbed behind same port. |
| `RenderTarget` | **reelee** (§6) | Frozen JSON projection → reelee Project / `PanelView`. |

---

## 4. The engine

`play(demoDoc, executor, observers) -> Outcome`: a pure walk emitting the lifecycle protocol
(`onDemoStart/End`, `onSectionEnter/Exit`, `onStepEnter` → `beforeCommand` →
`afterCommand`|`onCommandError` → `onStepExit`, `onCueBegin/End`, `onNarration`, `onBeat`).
Recorder, overlay, narrator, pacer, logger are **all just observers** composed as a list.

**Driver inversion = one core, two modes**, behind a `CommandSource`:

- **Generative:** a pull-iterator — `play` reads each `CommandStep.command` and calls
  `executor(command)`. In the acture world `executor` = `registry.dispatch`; the whole core
  reduces to a cue/narration/camera-aware `replaySequence`.
- **Capture:** a push-stream — an interception observer taps the live dispatch stream and
  *emits* Steps into a fresh Demo Document. The lifecycle protocol and every observer are
  identical to generative mode.

---

## 5. Capture-mode interception point (found)

`acture` already provides the exact seam, in
`acture/packages/e2e-playwright/src/sequence.ts`:

```ts
recordSequence(registry): { steps: SequenceStep[], stop() }   // wraps registry.dispatch
```

It monkey-patches `registry.dispatch`, pushing `{commandId, params}` after each successful
dispatch, and restores the original on `stop()` — structurally identical to
`acture-telemetry`'s `instrumentTelemetry` and `acture-devtools`' `instrumentRegistry`.

**walkthru's `ActionRecorder` adapter is a `recordSequence` superset:** same `dispatch` wrap,
but instead of bare `SequenceStep`s it emits `CommandStep`s into a Demo Document, and (in the
browser) co-records the rrweb time-base via `addCustomEvent(commandId, params)` so the
interaction stream and the command stream stay aligned. **The command-dispatch layer is the
source of truth; rrweb/pixels are the aligned side-channel.** The single primitive tapped is
`Registry.dispatch` (`acture/packages/core/src/registry.ts`).

---

## 6. Render hand-off: the real `reelee` contract (found)

`reelee` is a **MoviePy/ffmpeg Ken Burns** film generator, *not* a Remotion props renderer.
Entry point (`reelee/kenburns_video.py`):

```python
render_kenburns_video(project, out, *, strategy=None, target_total_s=60.0,
                      min_duration_s=2.0, fps=30, zoom=1.10, pan=0.03,
                      style="push", ease=False, ...) -> Path
```

The input is a `reelee.Project` graph; internally it projects to an ordered list of display
records (`reelee/storyboard_export.py`):

```python
@dataclass(frozen=True)
class PanelView:
    index: int; panel_id: str; caption: str; shot_id: str; framing: str
    camera: str; transition_in: str; notes: str; image_path: Optional[Path]
```

**First `RenderTarget` adapter (`ecosystem/reelee/`):** map the frozen JSON Demo Document →
an ordered `list[PanelView]`-equivalent (one panel per `CommandStep`/`Beat`: `caption` ←
narration text, `image_path` ← captured frame, `camera`/`framing`/`transition_in` ← camera
track + cue intent, per-panel duration ← Step `timing`), then either build a `reelee.Project`
and call `render_kenburns_video`, or call it directly with a `film_renderer`. Timing/fps/style
map to the kwargs. The renderer is free to ignore anything it does not understand.

`reelee-web` (Vite + React 19 + shadcn) is the **storyboard editor**, not a video renderer; it
already speaks `acture` for actions and `@zodal/core` for collections — a natural surface to
later *edit* Demo Documents, but out of MVP scope.

**Secondary `RenderTarget`s (build only when real):** Remotion (frozen JSON as input props),
OTIO (NLE round-trip), WebVTT/SRT (captions — nearly free from the narration track).

---

## 7. Reserved but NOT built (write the seam, write a note, move on)

- **Branching / non-linear flow** (`next: stepId | Branch`) — type-level seam only. The single
  feature most likely to trigger the inner-platform effect. Build when ≥3 demos need it.
- **Parallel cue choreography across sections**, **B-roll/PiP compositing**, **effects
  graphs**, **easing-curve DSLs** — these live in the *renderer*, never the schema.
- **A 6th+ cue type** — requires a rule-of-three justification in `DECISIONS.md`.
- **Self-healing locators** — ship as human-reviewed suggestions only, when real drift appears.
- **Desktop stack** (OBS/pywinauto/AX, OS-level click-through overlays) — Stage 4, only if
  demanded.

---

## 8. Order of work (each step keeps the core green)

1. **Schema SSOT** (Pydantic) + emitted JSON Schema + codegened Zod + round-trip test.
2. **Pure `core/`**: `play()`, lifecycle protocol, `CommandSource` (both directions), the
   seven port Protocols — fully unit-tested with **in-memory fakes**, zero vendor deps. Add
   the firewall CI check.
3. **One real adapter per essential port** for the web-first generative path (acture executor
   + Playwright recorder/locator + driver.js cues).
4. **Capture mode** producing the same Demo Document via the `dispatch` interception observer.
5. **Render hand-off**: the `reelee` `RenderTarget` (frozen JSON projection → Ken Burns).
6. **Narration**: `Transcriber`/`Synthesizer` with at least the draft tier (Web Speech /
   Piper) + WebVTT export; hosted-TTS stubbed behind the same port.
7. **Two runnable `examples/`** (generative + capture) + README quickstart.

Adapters must never be required to run core tests.

---

## 9. Open questions for the next sessions (tracked as issues)

- Exact field mapping Demo Document → `reelee.Project` (does walkthru build a Project, or feed
  `PanelView`s directly via a custom `film_renderer`?). Needs a closer read of
  `reelee/storyboard_export.py` + `kenburns_video.py`.
- Whether the Python `play()` mirror is needed for MVP, or TS-only suffices until render time.
- Where the codegen step lives (a `schema/` build script vs. reusing reelee-web's codegen
  toolchain).
- Whether to register the Demo Document as a `lacing` body schema in MVP or defer.
