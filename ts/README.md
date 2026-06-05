# acture-walkthru

The **TypeScript surface of [walkthru](https://github.com/thorwhalen/walkthru)** —
a Zod schema (and its inferred type) for the *Demo Document*, the editable,
re-renderable artifact that represents a demo/tour.

The schema is generated from walkthru's Python Pydantic single source of truth, so
a Demo Document produced anywhere — Python, a renderer, a capture tool — validates
and types identically here.

```bash
npm i acture-walkthru
```

## Validate a Demo Document

```ts
import { demoDocumentSchema, type DemoDocument } from "acture-walkthru";

const doc: DemoDocument = demoDocumentSchema.parse(JSON.parse(jsonString));
// Throws on unknown cue/step kinds or wrong field types — the unions are closed,
// and the wire format is camelCase (durationMs, holdAfterMs, stepId, …).
```

A minimal document:

```ts
const doc = {
  id: "demo-minimal",
  sections: [
    {
      id: "s1",
      steps: [
        { kind: "command", id: "step-1", command: { id: "app.open" },
          timing: { durationMs: 500 } },
      ],
    },
  ],
};
const validated = demoDocumentSchema.parse(doc); // -> typed DemoDocument
```

## What's here / what's coming

- **Now:** `demoDocumentSchema` (Zod validator) + the `DemoDocument` type.
- **Later:** the live capture/play engine over [`acture`](https://github.com/thorwhalen/acture).

The Python package [`walkthru`](https://pypi.org/project/walkthru/) owns the schema
SSOT, the pure play/capture engine, and the render hand-off.

## License

MIT
