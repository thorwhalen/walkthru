# walkthru

Turn a sequence of application **commands** into an **editable, re-renderable demo/tour
artifact** — and play that sequence while observers record video, draw visual cues, and
narrate.

`walkthru` owns the **representation** (the *Demo Document*) and the **playback/capture
engine**. It does **not** render the final video — it hands a validated artifact off to a
renderer (the `reelee` ecosystem, Remotion, moviepy/ffmpeg, …). *Owning representation, not
pixels, is the load-bearing boundary of the whole design.*

## Two modes, one data model, one engine

- **Generative** — an author supplies a Demo Document (commands + annotations); `walkthru`
  plays it while recording, with optional cues (highlight, spotlight, hotspot, callout,
  synthetic cursor), pauses, and narration.
- **Capture** — a human operates the app manually; `walkthru` records the video **and** the
  underlying command stream **and** annotations, producing the *same* Demo Document.

The only difference between the modes is *who fills in the document*.

## The core

```
play(demoDoc, executor, observers) -> Outcome
```

A pure higher-order function that walks the document and emits lifecycle events
(`onStepEnter` → `beforeCommand` → `afterCommand` → `onStepExit`, `onCueBegin/End`,
`onNarration`, …). It never records, renders, or speaks — every effect is an injected
observer or port.

## Ecosystem-biased, ecosystem-independent

The core and ports depend on **nothing** from our ecosystem. Integration with
[`acture`](https://github.com/thorwhalen/acture) (the command layer),
[`reelee`](https://github.com/thorwhalen/reelee) (the renderer), and `zodal` ships as
**optional adapters**. You can `pip install walkthru` / `npm i acture-walkthru` and use the
core with your own adapters.

## Packages

| Package | Registry | Role |
|---|---|---|
| `walkthru` | PyPI | Python core + schema SSOT + render hand-off |
| `acture-walkthru` | npm | TS core + the live capture/play engine over `acture` |

## Status

🚧 **Planning.** See [`PLAN.md`](./PLAN.md) for the implementation plan,
[`DECISIONS.md`](./DECISIONS.md) for design decisions and deviations from the brief, and the
repo's **enhancement issues** for the running development journal. Source documents live in
[`misc/docs/`](./misc/docs/).

## License

MIT — see [`LICENSE`](./LICENSE).
