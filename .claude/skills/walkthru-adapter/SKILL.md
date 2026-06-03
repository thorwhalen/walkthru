---
name: walkthru-adapter
description: >-
  How to implement a new port adapter for walkthru — a backend behind one of its
  Protocol ports — without breaking the core/adapter firewall. Use whenever you
  add or modify an integration: a new RenderTarget (Remotion, moviepy, ffmpeg), a
  new ElementLocator or Recorder (Selenium, Puppeteer, OBS), a CueRenderer,
  Transcriber (Whisper), Synthesizer (Piper/TTS), CommandPlayer, or ActionRecorder
  — or when wiring walkthru to acture/reelee or any vendor SDK. Also use when
  `tests/test_firewall.py` fails ("core import pulled in firewalled modules") or
  when deciding where vendor code belongs. Trigger even if the user just says "add
  a Remotion renderer", "make walkthru work with Selenium", or "implement the
  recorder for X".
---

# Implementing a walkthru adapter

Every effect walkthru performs is injected through a `Protocol` **port** in
`walkthru/ports/__init__.py`. An *adapter* is a concrete backend that satisfies a
port. The non-negotiable rule is the **firewall**: the pure core
(`walkthru/core`, `walkthru/ports`) must import **nothing** from any adapter,
ecosystem package, or vendor SDK. `tests/test_firewall.py` enforces it by
importing the core with a clean module table and asserting none of these leaked:
`walkthru.adapters`, `walkthru.ecosystem`, `playwright`, `obsws`, `whisperx`,
`piper`, `acture`, `reelee`. If you break that, the failure is immediate.

This is what makes `pip install walkthru` usable with *your own* adapters and
keeps any one vendor from becoming a hard dependency.

## The eight ports (pick the one you're implementing)

All are `@runtime_checkable` Protocols; methods are `async`.

| Port | Method | Role |
|---|---|---|
| `CommandPlayer` | `play(command: Command) -> Any` | run one command (the executor) |
| `Recorder` | `start() -> None`, `stop() -> AssetRef` | record screen to media |
| `ActionRecorder` | `record() -> AsyncIterator[CommandInvocation]` | capture-mode input stream |
| `ElementLocator` | `bounds(target: Target) -> Rect` | resolve a `Target` to live geometry |
| `CueRenderer` | `show(cue: Cue, rect: Rect \| None = None) -> None` | draw a cue |
| `Transcriber` | `transcribe(audio: AssetRef) -> list[WordTiming]` | speech → word timings |
| `Synthesizer` | `say(text: str) -> AssetRef` | text → speech audio |
| `RenderTarget` | `export(artifact: DemoDocument) -> AssetRef` | Demo Document → rendered video |

You don't subclass these — Protocols are structural. Match the method signatures
and you satisfy the port.

## Where adapter code lives

- A vendor/tooling adapter → `walkthru/adapters/<vendor>/`
  (e.g. `walkthru/adapters/playwright/`, `walkthru/adapters/export/`).
- An ecosystem integration (our own stack: acture, reelee) →
  `walkthru/ecosystem/<name>/` (e.g. `walkthru/ecosystem/reelee/`).

Either way it is **downstream** of the firewall: it may import from
`walkthru.core` and `walkthru.ports`, never the other way around.

## The pattern (study the two worked examples first)

The cleanest references already in the tree:

- `walkthru/adapters/playwright/` — `PlaywrightElementLocator` and
  `PlaywrightRecorder`. Note it **imports nothing from `playwright` at module
  top**: it drives an injected, duck-typed `page` object. That's why
  `test_playwright_adapter.py` runs with fakes and no browser installed.
- `walkthru/ecosystem/reelee/render_target.py` — `ReeleeRenderTarget` plus the
  pure mapping functions (`timeline_to_panels`, `timeline_to_plans`,
  `render_plans`, `render_demo_video`). It maps a resolved timeline onto reelee's
  `PanelView` contract rather than reconstructing reelee's internal graph.

Follow these principles:

1. **Inject the vendor object; don't import the SDK at module scope.** Take the
   browser/page/renderer/client as a constructor argument. If you must touch the
   SDK, import it lazily *inside* the method, or keep it behind the optional
   extra. Module-top `import playwright` in an always-loaded path is exactly what
   the firewall test catches. (Adapter modules are only imported when the user
   opts in, so an SDK import there is fine — but keeping it duck-typed lets the
   adapter be unit-tested without the SDK, which is the project's standard.)

2. **Translate at the boundary; let no vendor type leak inward.** Convert vendor
   results into the core types (`Rect`, `AssetRef`, `WordTiming`, …) before
   returning. The core never sees a vendor object.

3. **Do the time math via the timeline, not by hand.** Render/animation adapters
   should consume `resolve_timeline(document)` (or `iter_resolved_steps`) and read
   absolute `start_ms`/`end_ms`. Don't re-derive timing from raw durations — the
   composition rules (hold-after, anchor offsets, narration spans) live in
   `walkthru/core/timeline.py` and are tested there.

4. **Keep pure mapping separate from the I/O drive.** reelee splits
   `timeline_to_panels` / `timeline_to_plans` (pure, trivially testable) from
   `render_plans` / `render_demo_video` (the actual render). Mirror that split so
   most of your adapter is testable without running the backend.

## Declare the optional dependency

Add an extra in `pyproject.toml [project.optional-dependencies]` so the backend
installs on demand but is never a core dependency:

```toml
[project.optional-dependencies]
yourvendor = ["yourvendor-sdk"]
```

The core's only runtime dependency is `pydantic>=2`; keep it that way.

## Test with fakes, then (optionally) for real

- Write an in-memory fake that satisfies the port and add it alongside the
  existing ones in `tests/fakes.py`; assert your adapter's behavior against it —
  no SDK required. This is the primary test.
- Add a focused test module (mirror `tests/test_playwright_adapter.py` /
  `tests/test_reelee_target.py`).
- Run the firewall test to confirm you didn't leak:
  ```bash
  pytest tests/test_firewall.py tests/test_<your_adapter>.py -v
  ```
- If you added a forbidden-by-default vendor that the core must still never pull
  in, add its top-level package name to `FORBIDDEN_PREFIXES` in
  `tests/test_firewall.py` so the guard covers it too.

## Quick checklist

- [ ] Adapter lives under `walkthru/adapters/<vendor>/` or `walkthru/ecosystem/<name>/`
- [ ] Satisfies the port's method signatures (structural — no subclassing)
- [ ] Vendor object injected; no vendor type crosses back into the core
- [ ] Render/animation adapters consume `resolve_timeline()` for absolute times
- [ ] Pure mapping split from I/O drive
- [ ] Optional extra added in `pyproject.toml`; core still depends only on pydantic
- [ ] Fake-based test added; `tests/test_firewall.py` green
