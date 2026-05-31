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

## D6. Flat package layout, `py/` + `ts/` split — **[call]**

**Brief proposed:** `py/src/walkthru/…`.

**Decision:** flat layout — `py/walkthru/…` (package dir at the `py/` root, no `src/`) —
matching `dol`/`nw`/`reelee` (hatchling, flat, `requires-python >= 3.10`, ruff with `D100`
module-docstring enforcement, wads uv-CI). The `py/` + `ts/` top-level split hosts both
languages in one repo as the brief intends; the JSON Demo Document is the only thing that
crosses between them.

---

## D7. Pydantic v2 over plain dataclasses for the Python SSOT — **[call]**

The brief left the Python mirror open (dataclasses / pydantic / generated). Chose **Pydantic
v2**: it gives validation *and* JSON-Schema emission in one step (the whole point of the SSOT),
and it is what the federation already uses, so `lacing` schema registration and the reelee
round-trip come for free. The `core` remains pure — schema validation is side-effect-free; only
`play()`'s injected observers/ports perform effects.

---

## Open judgment calls deferred to issues (not yet decided)

- Whether `play()` needs a **Python mirror** for MVP or whether TS-only suffices until render.
- **Where codegen runs** (a `schema/` build script vs. reusing reelee-web's toolchain).
- Demo Document → `reelee.Project` field mapping: build a `Project`, or feed `PanelView`s via a
  custom `film_renderer`.
- Whether to register the Demo Document as a **`lacing` body schema** in MVP or defer.

These are tracked as enhancement issues — the project's permanent development memory.
