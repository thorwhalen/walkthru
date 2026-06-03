---
name: walkthru-dev
description: >-
  Orientation and conventions for working ON the walkthru codebase itself (the
  Python core + the TypeScript `acture-walkthru` package). Use this whenever you
  are editing, refactoring, testing, or reviewing code inside the walkthru repo —
  adding a module, changing the engine/timeline/ports, wiring CI, running the test
  suites, or figuring out where something belongs. Start here to get the mental
  model, then hand off to `walkthru-schema` for Demo Document schema changes or
  `walkthru-adapter` for new port adapters. Trigger even if the user just says
  "let's work on walkthru" or names an internal module (engine, timeline, ports,
  reelee target, playwright adapter) without spelling out the architecture.
---

# Developing walkthru

walkthru turns a sequence of app **commands** into an **editable, re-renderable
demo/tour artifact** (the *Demo Document*) and plays/captures that sequence while
observers record video, draw cues, and narrate. The one sentence that governs
every design choice: **walkthru owns the representation, not the pixels.** It
hands a validated artifact to a renderer; it never draws the final video itself.

Read this file first to orient. For the two workflows that are easy to get wrong,
defer to the specialized skills:

- Changing the Demo Document data model → **`walkthru-schema`** (the Python↔TS
  codegen seam has drift guards that fail CI if you skip a step).
- Implementing a new port backend (renderer, locator, recorder, …) →
  **`walkthru-adapter`** (the firewall is enforced by a test).

## The mental model (four load-bearing ideas)

1. **One data model, two modes.** *Generative* play (author supplies the
   document, walkthru plays it while recording) and *capture* (a human drives,
   walkthru records the video **and** the command stream) produce the **same**
   `DemoDocument`. The only difference is who fills it in.

2. **A pure engine.** `play(document, executor, *, observers) -> Outcome` walks
   the document and emits a typed lifecycle event stream
   (`DemoStart → SectionEnter → StepEnter → BeforeCommand → AfterCommand →
   StepExit → … → DemoEnd`, plus `CueBegin/End`, `Narration`, `BeatEvent`). It
   never records, renders, or speaks. Every effect is an injected **observer** or
   **port**. Keep it that way — effects belong in observers/adapters, not the
   engine.

3. **The firewall.** `walkthru/core` and `walkthru/ports` depend on **nothing**
   from our ecosystem or any vendor. Integrations (Playwright, reelee, acture)
   are optional extras that depend on the ports, never the reverse. No vendor
   type ever crosses a port. `tests/test_firewall.py` enforces this — if you find
   yourself importing an adapter from core, stop.

4. **Relative time + anchors.** The SSOT stores only relative durations
   (`durationMs`, `holdAfterMs`) — never absolute timestamps. Cues, narration,
   and camera live in parallel `tracks` and attach to steps by **anchor**
   (`{stepId, localOffsetMs}`), not by fields stored on the step. Absolute time
   is *derived* by `resolve_timeline()`. This avoids a dual source of truth.

## Repo map

```
walkthru/                  # Python: the SSOT + pure engine + ports + adapters
  __init__.py              # the public API surface (re-exports from core)
  core/
    schema.py              # ★ THE SSOT: Pydantic v2 Demo Document models
    engine.py              # play() and record() — the pure engine
    events.py              # the lifecycle events + Observer/Outcome types
    timeline.py            # relative→absolute composition (resolve_timeline)
  ports/__init__.py        # 8 Protocol port interfaces (the firewall boundary)
  adapters/
    playwright/            # ElementLocator + Recorder over a Playwright page
    export/                # dependency-free: JSON target + WebVTT captions
  ecosystem/reelee/        # first real RenderTarget: Demo Document → Ken Burns mp4
schema/
  demo-document.schema.json  # committed JSON Schema emitted by schema.py (guarded)
  fixtures/                   # minimal-demo.json, full-demo.json (cross-lang contract)
ts/                        # TypeScript: the npm package `acture-walkthru`
  src/schema.generated.ts  # codegened Zod — DO NOT edit by hand
  scripts/codegen.mjs      # JSON Schema → Zod codegen (+ --check drift guard)
  src/*.test.ts            # vitest: roundtrip + codegen-drift
tests/                     # pytest: schema, engine, timeline, firewall, adapters
  builders.py              # make_minimal_demo / make_rich_demo / make_full_demo
  fakes.py                 # in-memory fake ports for tests
```

## Conventions

- **Public API goes through `walkthru/__init__.py`.** New user-facing symbols
  must be re-exported there (it's the documented surface and the test/round-trip
  anchor). Internal helpers stay underscore-prefixed and module-local.
- **Wire format is camelCase; Python is snake_case.** Pydantic models inherit a
  base that aliases automatically. Dump with `by_alias=True`.
- **Discriminated unions** key off a literal field (`Step.kind`, `Cue.type`).
  Adding a variant is a schema change — see `walkthru-schema`.
- **Module docstrings are required** (ruff `D100`, Google convention). Every new
  module needs a top-level docstring; they're auto-extracted for docs.
- **Sync or async, both fine.** Executors and observers may be either; the engine
  normalizes via `_maybe_await`. Don't assume one or the other.

## Running the tests

Two independent suites — run the one(s) you touched, and both before a schema
change lands.

```bash
# Python core (no optional extras needed for the core/engine/timeline/firewall tests)
pytest -v --tb=short

# A single area
pytest tests/test_engine.py -v

# TypeScript (from the ts/ subdir)
cd ts && npm ci && npm test
```

The Playwright and reelee tests use **fakes** (`tests/fakes.py`) and duck-typed
injection, so they run without the real vendor libraries installed. Install the
extras (`pip install -e ".[playwright]"` / `".[reelee]"`) only when you need to
exercise a real backend.

## CI (dual-track, both via i2mint/wads reusable workflows)

- **Python** — `.github/workflows/ci.yml` → wads `uv-ci.yml`. Config is the SSOT
  in `pyproject.toml [tool.wads.ci]`. Publishing to PyPI is **enabled** and
  automatic on every push to `main` that passes validation (auto-version-bump);
  marker `[publish]`, skip with `[skip ci]`.
- **TypeScript** — `.github/workflows/npm-ci-ts.yml` → wads `npm-ci.yml`. Runs
  only on `ts/**` changes. Config lives in `ts/package.json` under `wads.ci`.
  Publishing to npm is **per-commit, opt-in**: it needs the `[publish-npm]`
  marker in the commit message AND a push to `main`. There is **no auto-bump** on
  the JS side — it publishes exactly the `version` in `ts/package.json`.

⚠️ **The `[skip ci]` footgun:** GitHub's built-in skip detection scans the
*entire* commit message, body included. Never write the literal `[skip ci]`
inside an explanatory sentence in a commit body, or the whole push is skipped —
this already cost the project its first npm publish (PR #12). If you need to
mention the marker in prose, break it up (e.g. `skip-ci`) so it isn't matched.

## Design docs

`PLAN.md` (implementation plan), `DECISIONS.md` (design decisions and deviations,
referenced as §D2, §D6, …), and source docs in `misc/docs/`. The running dev
journal lives in the repo's GitHub issues. Read the relevant decision before
reversing one.
