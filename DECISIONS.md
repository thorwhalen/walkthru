# walkthru — Decisions & Deviations

> Deliverable 2 of the build brief. Every place this project deviates from
> `misc/docs/WALKTHRU-AGENT-BRIEF.md` or either report, plus every genuinely open judgment
> call — with the reasoning and what in the code justified it. Candid, not deferential, per
> the brief's instruction. Granular follow-up lives in the repo's enhancement issues.

Legend: **[deviation]** departs from a stated brief/report conclusion · **[call]** an open
judgment the brief left to us · **[confirm]** inspection confirmed a brief assumption.

---

## D1. SSOT authored in Python (Pydantic), not Zod-first — **[deviation]**

**Brief said:** Zod is the presumptive SSOT; `zodal` is the presumptive schema layer; author
the Demo Document in TS-Zod / `zodal` and emit JSON Schema for the renderer.

**Decision:** Author the SSOT **once in Python Pydantic v2**; emit JSON Schema; **codegen Zod
v4** for the TS side.

**What justified it:**

- `reelee` defines its content schemas as **Pydantic** `BaseModel`s registered via
  `lacing.register_body_schema`, exports JSON Schema (`reelee export-schemas`), and
  **`reelee-web` codegens its Zod types from that export** (`schemas/` → `src/types/generated/`,
  never hand-written). The federation's SSOT direction is **Python → JSON Schema → Zod**, the
  opposite of the brief's bias.
- Matching this lets the Demo Document register as a `lacing` body schema and round-trip
  losslessly with the renderer side, instead of fighting the grain of the ecosystem.
- `zodal` turned out to be **collection-centric** (`defineCollection`, `DataProvider`,
  list/filter/sort) and TS-only — a poor fit for authoring a single nested document schema. It
  is the right tool for *presenting a library of* Demo Documents/Steps as a collection, not for
  defining the document itself.

**Cost / risk:** the *live* engine runs TS-side (capture taps acture in the browser), so TS
consumes codegened types rather than authoring them. This is exactly how `reelee-web` already
operates, so the toolchain exists. Ecosystem-independence is preserved: Pydantic is a
permissive third-party dep, not an ecosystem package; the `lacing` hook is an optional
`ecosystem/` adapter.

---

## D2. First `RenderTarget` is reelee's Ken Burns contract, not Remotion — **[deviation]**

**Brief/report said:** treat the hand-off as Remotion-style "input props"; Report 02 used
Remotion as a proxy because "Reelee could not be identified from public sources."

**Decision:** The first `RenderTarget` adapter targets **`reelee`'s actual contract** — a
`reelee.Project` graph projected to an ordered `list[PanelView]`, rendered by
`render_kenburns_video(project, out, ...)` (MoviePy/ffmpeg). Remotion becomes a *secondary,
external* adapter built only if a real need appears.

**What justified it:** `reelee` is a real, inspectable ecosystem package and is **not** a
React/props renderer. Its render input is `PanelView` records (`reelee/storyboard_export.py`) +
`render_kenburns_video` kwargs (`reelee/kenburns_video.py`). The brief itself instructed:
"inspect `reelee`'s actual input contract and write the first `RenderTarget` adapter against
it — the real contract supersedes the Remotion proxy; only the field-mapping adapter changes."
This decision follows that instruction.

**Unchanged:** the boundary principle (we own representation, the renderer owns pixels; hand off
validated JSON; the renderer may ignore what it doesn't understand) holds exactly as written.

**Resolved (was an open question): feed `PanelView`s, don't rebuild a `reelee.Project`.** Issue #3
left open whether the adapter constructs a `reelee.Project` graph or feeds panels directly.
`render_kenburns_video(project, …)` immediately calls `collect_panel_views(project)` — it
re-derives panels from an `nw`/`lacing`/falaw annotation + content-addressed-artifact graph.
Reconstructing that graph from a `DemoDocument` would bleed reelee's whole internal model across
the firewall, only for reelee to throw our panels away and rebuild its own. So
`walkthru.ecosystem.reelee` maps the resolved `Timeline` **directly** to `list[PanelView]` and
drives the film with the *same lower-level primitives* `render_kenburns_video` uses internally
(`burns.ken_burns_path` + an injectable `film_renderer`, default
`reelee.kenburns_video.default_film_renderer`). Per-panel screen time comes from the **walkthru
timeline** (the SSOT already composes it), not reelee's shot-timing strategies. The step-level
`poster` (AssetRef) added in this work is the panel image (`PanelView.image_path`).

---

## D3. The command layer is `acture`; reuse its record/replay primitives — **[confirm + call]**

**Brief said:** reuse the command layer's registry + middleware; find the cleanest capture
interception point.

**Finding:** the layer is **`acture`** (TS/React, Apache-2.0). It already ships, in
`acture/packages/e2e-playwright/src/sequence.ts`:

- `replaySequence(registry, sequence, {ctx, onStep, stopOnError})` — generative replay.
- `recordSequence(registry) → {steps, stop()}` — capture, by wrapping `registry.dispatch`.

**Decision/call:** `walkthru`'s `play()` is a cue/narration/camera-aware **superset of
`replaySequence`**, and its `ActionRecorder` is a Demo-Document-emitting **superset of
`recordSequence`**. We do **not** invent a new engine or a new extension paradigm — observers
wrap `registry.dispatch` exactly as `acture-telemetry`/`acture-devtools` already do. acture has
**no core middleware chain by design** (dispatch interception is an opt-in adapter concern);
`acture-walkthru` slots in as one more opt-in dispatch-observer package beside
`acture-e2e-playwright` and `acture-telemetry`.

**Implication:** much of the TS engine is *composition over acture*, not new code. This is the
single biggest scope reduction inspection produced.

---

## D4. Command atom mirrors acture's `SequenceStep {commandId, params}` — **[confirm]**

The brief's `command:{id, params}` maps to acture's macro step shape exactly:
`SequenceStep { commandId: string, params?: unknown }` (`sequence.ts`). The full command
*definition* is a richer `CommandRecord {id, title, params: ZodType, when, execute, …}`, but
the *serializable macro step* — what a Demo Document stores — is `{commandId, params}`. We adopt
`{ command: { id, params } }` in the Demo Document and bridge `id ↔ commandId` in the acture
adapter. acture constrains `params` to the JSON-Schema-representable Zod subset; our Pydantic
models honor the same subset so codegen stays faithful.

---

## D5. License = MIT — **[call]**

**Brief said:** pick a permissive license consistent with the ecosystem.

**Decision:** **MIT.** The Python house default across `dol`, `nw`, `lacing`, `reelee`, and
`zodal` is MIT. `acture` is the lone **Apache-2.0** package; since `acture-walkthru` builds on
acture, Apache-2.0 is the relevant *inbound* license, and MIT is outbound-compatible with it
(MIT code may depend on Apache-2.0). MIT keeps walkthru aligned with the Python orbit it
publishes into while remaining compatible with the acture tie.

---

## D6. Layout = wads current defaults (Python `name/name/` at root); frontend CI deferred — **[call]**

**Brief proposed:** `py/src/walkthru/…`. An earlier draft of this doc used a `py/` + `ts/`
split. Both are superseded.

**Decision:** Use **wads current defaults**. The Python package sits at the **repo root** in the
`name/name/` form — `walkthru/walkthru/` — exactly what `wads populate` produces (hatchling,
`requires-python >= 3.10`, MIT, ruff `D100`, `tests/`, `[tool.wads.ci.*]` SSOT, the 5-line
`.github/workflows/ci.yml` uv stub, plus the wads `.gitignore`/`.gitattributes`/`.editorconfig`).
The TypeScript side lives in a sibling **`ts/`** subdir as a **single** npm package
(`acture-walkthru`).

**What justified it (and the constraint):** the user maintains ~200 repos in the `name/name`
form and wants the Python convention left untouched. wads already models the frontend as a
*separate, additive* overlay (`profiles.py` / `npm_config.py` + a path-filtered workflow), so
supporting a TS frontend alongside the unchanged Python layout costs nothing. Confirmed by
reading wads: `populate` (Python) and `apply_npm_overlay` (frontend) are independent code paths.

**Frontend CI deferred — coordination, not indecision.** wads' frontend overlay is brand-new and
unused (zodal was set up independently/earlier), so its defaults can change freely. We filed
**i2mint/wads#39** to generalize the single npm overlay into a **js/ts language-profile
registry** (extensible, with a monorepo seam), to be built in a separate session. To avoid the
two sessions colliding, walkthru:

- ships the **Python side on wads current defaults now** (this commit), with a **Python-only**
  `ci.yml`; and
- **defers `ts/` scaffolding + `npm-ci.yml`** until the wads `ts` profile lands, then generates
  them via `wads --frontend ts`.

**Single TS package, not a monorepo (for MVP).** `acture`/`zodal` are pnpm+turbo monorepos, but
walkthru's MVP needs only one publishable package. The core/adapter firewall is enforced
*within* one package (subpath exports + an import-boundary lint such as dependency-cruiser +
optional peer deps) — separate packages would be premature. The wads single-package overlay
fits; we graduate to the `ts-monorepo` profile (reserved in #39) only if adapters ever need
independent versioning.

**Pre-release CI toggles.** Because there is no release artifact, generated docs, or metrics
history yet, `[tool.wads.ci].publish/docs/metrics` are set to `enabled = false` (testing +
ruff stay on so CI gives real signal). Flip `publish` on at the first release; `docs` on once
docs exist. This is a phase toggle, not a convention change.

---

## D7. Pydantic v2 over plain dataclasses for the Python SSOT — **[call]**

The brief left the Python mirror open (dataclasses / pydantic / generated). Chose **Pydantic
v2**: it gives validation *and* JSON-Schema emission in one step (the whole point of the SSOT),
and it is what the federation already uses, so `lacing` schema registration and the reelee
round-trip come for free. The `core` remains pure — schema validation is side-effect-free; only
`play()`'s injected observers/ports perform effects.

---

## D8. Anchor is the single SSOT for cue/narration → step association — **[call]**

**Brief listed** `cueRefs?` and `narrationRef?` on `CommandStep`, *and* anchors on the cue and
narration tracks — i.e. the association stored in two places.

**Decision:** Drop the step-side `cueRefs`/`narrationRef`. The **track item's `anchor`**
(`{stepId, localOffsetMs[, durationMs]}`) is the *only* place a cue/narration is tied to a step.
The engine resolves "what fires at this step" by filtering the tracks on `anchor.stepId`
(`_cues_for` / `_narration_for`).

**Why:** storing the same association on both the step and the track item is a dual-source-of-truth
that drifts on every edit (the user's SSOT principle, and Report 02's "wrong abstraction"
warning). The anchor is also strictly richer — it carries `localOffset` (and `duration` for
narration) that a bare id reference cannot — so it must exist regardless; the step-side ref is pure
redundancy. Finding a step's cues is an O(n) track scan, which is irrelevant at demo sizes. If a
real need for fast reverse lookup ever appears, it is a derived index, not new SSOT.

---

## D9. Lifecycle protocol realized as a typed event stream, not named hooks — **[deviation]**

**Brief/Report 02 §B.1** describe the lifecycle as an `Observer` object with named methods
(`onStepEnter`, `beforeCommand`, `onCueBegin`, …).

**Decision:** Realize it as a stream of **typed event dataclasses** (`StepEnter`, `BeforeCommand`,
`CueBegin`, …) consumed by observer **callables** (`Observer = Callable[[Event], Awaitable|None]`).
Each event type maps 1:1 to a brief hook name, so nothing is lost; the canonical walk is the async
generator `iter_events(document, executor)`, and `play()` is a thin driver that fans events to
observers.

**Why:** it matches Thor's functional-over-OOP convention and the iterables guidance (a lazy
`yield`-based stream rather than an object with 13 optional override points). Composition is
trivial (an observer is just a function; filtering by `isinstance` selects the events you care
about), and the same event vocabulary serves both `play` (generative) and `record` (capture) —
the "one lifecycle protocol, driver inverted" the brief wants. A named-hook adapter can be layered
on later for anyone who prefers it (progressive disclosure), but it is not the core mechanism.

**Async core — [call].** The engine and ports are `async` because the real executors (acture
dispatch, Playwright) and recorders do I/O. The pure-core tests need no async plugin — they use
`asyncio.run` over fakes. `executor` and observers may be sync *or* async; the engine awaits
whatever is awaitable (`_maybe_await`).

---

## D10. Zod codegen is a self-contained `ts/` build script, not reelee-web's toolchain — **[call]**

**Open question (was PLAN §9):** where the Zod codegen lives — a `schema/` build script vs.
reusing reelee-web's codegen toolchain.

**Decision:** a self-contained `ts/scripts/codegen.mjs` that consumes the committed
`schema/demo-document.schema.json` (the Pydantic-emitted artifact) and writes
`ts/src/schema.generated.ts`. It uses the **same tools** reelee-web uses — `json-schema-to-zod` +
zod v4 — but **not** reelee's `export-schemas` CLI or `lacing` body-schema registry.

**Why:** reelee-web's `scripts/codegen.mjs` is coupled to `python -m reelee export-schemas` and a
`lacing` `index.json` registry — machinery walkthru does not have, and whose adoption PLAN §9 still
defers (the `lacing` body-schema question). Reusing the *technique* without the *coupling* keeps
the TS side runnable with no Python toolchain and preserves the core/adapter firewall: TS depends
only on the JSON contract, never on `walkthru`/`reelee`/`lacing`.

**Two gotchas handled:** (1) `json-schema-to-zod` does **not** dereference `$ref` (CLI *or* API) —
it renders Pydantic's `$defs` refs as `z.any()`; we inline them first with
`@apidevtools/json-schema-ref-parser` (the Demo Document schema is a DAG, so full dereference is
safe). (2) Drift is guarded both sides: Python pins JSON Schema ↔ Pydantic
(`test_committed_json_schema_is_up_to_date`); TS pins the committed Zod ↔ JSON Schema via
`codegen.mjs --check` (run by `ts/src/schema.codegen.test.ts`). Discriminated unions arrive as
`oneOf` → json-schema-to-zod's "exactly one variant passes" `superRefine`, which is faithful
(closed union; unknown `type`/`kind` rejected — covered by the round-trip negatives).

---

## D11. Inner-platform-effect guardrails: reserve the seam, don't build it — **[call]**

**The standing risk (brief §8, PLAN §7, issue #6):** walkthru's dominant failure mode is the
**inner-platform effect** — slowly re-inventing a video editor inside the schema. The governing
sentence is *walkthru owns the representation, not the pixels*: the schema models **intent and
annotation**; all compositing, easing curves, and transitions live in the **renderer**, which
receives a validated artifact and is handed off to.

**Decision:** keep this line bright by *reserving type-level seams but not building features*, and
by enforcing the machine-checkable half in CI rather than trusting prose. The reserve-don't-build
list (each shipped only on the stated trigger):

| Reserved seam | Status in code | Build trigger |
|---|---|---|
| Branching / non-linear flow (`CommandStep.next`) | typed, defaults `None`, **never traversed** by the engine | **≥3 real demos** need it |
| Parallel cue choreography, B-roll/PiP compositing, effects graphs, easing-curve DSLs | **renderer domain — never in the schema** | n/a (out of scope by design) |
| A 6th+ cue type | five proven variants (`highlight/spotlight/hotspot/callout/cursor`) | **rule-of-three** recorded here (≥3 types sharing ≥80% handler code) |
| Self-healing locators | `Target` carries fallbacks/bbox/scrollAnchor; re-resolution is a *suggestion* | ship as **human-reviewed** suggestions when real drift appears — never a silent SSOT rewrite |
| Desktop stack (OBS/pywinauto/AX, OS-level overlays) | not present | Stage 4, only if demanded |

And the hard "do NOT"s: no vendor/ecosystem type crosses into `core/`/`ports/`; no absolute time
in the SSOT (only relative durations/offsets, global time derived by `resolve_timeline` — see
§D8); emit a validated artifact, **don't embed a renderer**.

**Why a decision entry and not just an issue:** issue #6 is the permanent human-facing reminder,
but an open issue is fragile memory — it can be closed or lost. The durable home for the *why* is
here; #6 stays open as the standing reminder and points at this entry.

**Enforcement (the prose is now partly executable):**
- `tests/test_firewall.py` — no vendor/ecosystem import reaches `core`/`ports`.
- `tests/test_guardrails.py` — exactly the five cue types and three beat kinds (a new one fails
  the test, forcing the rule-of-three conversation); no absolute-time field in the SSOT; and a
  *behavioral* guard that the engine plays in linear document order and never follows `next`.

A failing guardrail test is a **deliberate decision point**: if a guardrail must move, change the
assertion *and* record the justification here first — don't loosen the test to make a change pass.

---

## Open judgment calls deferred to issues (not yet decided)

- Whether `play()` needs a **Python mirror** for MVP or whether TS-only suffices until render.
- Whether to register the Demo Document as a **`lacing` body schema** in MVP or defer.

These are tracked as enhancement issues — the project's permanent development memory.
