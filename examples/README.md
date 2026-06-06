# walkthru examples

Two runnable scripts, one per mode, sharing one data model and one engine. Both are
**pure core** — they import only `walkthru` (which depends only on Pydantic), so they run
straight after `pip install walkthru` (or `pip install -e .` in this repo) with no optional
adapters and no ffmpeg.

```bash
python examples/generative_demo.py
python examples/capture_demo.py
```

## `generative_demo.py` — author a document, play it

The author supplies a Demo Document (commands + cues + narration); [`play()`](../walkthru/core/engine.py)
walks it, calls an `executor` for each command, and emits a lifecycle event stream that
observers subscribe to. The script then shows the **renderer hand-off**: the frozen JSON
projection a renderer consumes, and WebVTT captions derived from the narration track.

Demonstrates: authoring from the top-level `walkthru` facade · a command/beat mix · highlight
and callout cues anchored by `(stepId, localOffsetMs)` · a logging observer ·
`to_json` + `narration_to_webvtt`.

## `capture_demo.py` — record a human, replay it

Capture mode inverts the driver: a human operates the app, each command is observed *after the
fact* as a `CommandInvocation`, and [`record()`](../walkthru/core/engine.py) assembles those
into the **same** Demo Document — emitting the **same** lifecycle events, so observers behave
identically. The script then replays the captured document through `play()` and asserts the
replay reproduces the captured commands exactly.

Demonstrates: the two modes are **inverses over one data model** — capture → document → play
round-trips losslessly.

## Where the real adapters plug in

These examples use an in-memory `executor` and a fixed invocation stream so they stay
dependency-free. In a live run those seams are filled by adapters behind the
[ports](../walkthru/ports/__init__.py): the executor by `acture`'s `registry.dispatch` or a
Playwright `page`; the capture stream by an `ActionRecorder` tapping the live command bus; the
JSON hand-off by the [`reelee` render target](../walkthru/ecosystem/reelee/render_target.py)
for an actual Ken Burns video. Swapping any of them requires no change to the core or to these
documents — that is the whole point of the firewall (see [`PLAN.md`](../PLAN.md) §2, §3.4).
