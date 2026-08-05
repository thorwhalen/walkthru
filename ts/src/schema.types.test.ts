// The input/output type split of the generated schema (issue #24).
//
// One Zod schema induces TWO TypeScript types, and conflating them is the DX bug this file guards:
//
//   DemoDocument      = z.infer<typeof demoDocumentSchema>   // POST-parse: defaults are PRESENT
//   DemoDocumentInput = z.input<typeof demoDocumentSchema>   // PRE-parse:  defaults are OPTIONAL
//
// Before `DemoDocumentInput` existed, annotating a literal `: DemoDocument` demanded every field
// the runtime defaults (`meta.schemaVersion`, `command.params`, `timing.holdAfterMs`, …), so the
// README and tests simply dropped the annotation and lost type checking entirely.
//
// These are COMPILE-TIME assertions, checked by `npm run lint` (`tsc --noEmit`, which includes
// `src/**`), not by the vitest runtime. The `@ts-expect-error` below is the load-bearing half: it
// fails the build if the post-parse type ever silently becomes as permissive as the input type
// (e.g. if someone "fixes" #24 by swapping the alias to `z.input`, which would make `parse()`
// results claim their defaulted fields might be missing).
//
// The single runtime test then pins the behaviour those types describe: parsing fills the defaults.

import { describe, expect, it } from "vitest";

import {
  demoDocumentSchema,
  type DemoDocument,
  type DemoDocumentInput,
} from "./index.js";

/** A hand-written literal that omits every field the schema defaults. */
const literal = {
  id: "demo-typed",
  meta: { title: "Typed" },
  sections: [],
};

// Compiles: pre-parse, `meta.description` / `meta.schemaVersion` are optional.
const asInput: DemoDocumentInput = literal;

// @ts-expect-error — post-parse, `meta.description` and `meta.schemaVersion` are REQUIRED, so a
// bare literal is not a `DemoDocument`. If this line ever stops erroring, the two types have
// collapsed into one and the distinction #24 asked for is gone.
const asOutput: DemoDocument = literal;

describe("DemoDocument vs DemoDocumentInput", () => {
  it("parsing an input literal yields the post-parse type with defaults filled", () => {
    const parsed: DemoDocument = demoDocumentSchema.parse(asInput);
    expect(parsed.meta).toEqual({
      title: "Typed",
      description: null,
      schemaVersion: "0.1.0",
    });
    // `asOutput` exists only to carry the @ts-expect-error above; touch it so no
    // "declared but never read" configuration can drop the assertion.
    expect(asOutput).toBe(literal);
  });
});
