// The Python↔TS round-trip seam (PLAN §1, §8.1; closes the last acceptance criterion of #5).
//
// The Pydantic models in walkthru/core/schema.py are the SSOT. They emit the committed fixtures
// in schema/fixtures/ (each guarded on the Python side by tests/test_schema.py — every fixture
// re-parses to exactly its builder). Here we prove the OTHER half: those same Python-authored JSON
// documents validate against the codegened Zod, and parsing preserves them byte-for-byte. Together
// the two suites show a DemoDocument round-trips Python→JSON→Zod→JSON without drift — the two sides
// are interchangeable over the one wire format.

import { readFileSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { demoDocumentSchema } from "./schema.generated.js";

const FIXTURE_DIR = resolve(
  dirname(fileURLToPath(import.meta.url)),
  "../../schema/fixtures",
);

const loadFixture = (name: string): unknown =>
  JSON.parse(readFileSync(resolve(FIXTURE_DIR, name), "utf8"));

const FIXTURES = ["minimal-demo.json", "full-demo.json"];

// A field the Python side omits entirely when unset (currently only AssetRef.rights — see
// walkthru/core/schema.py's model_serializer, added for thorwhalen/illustration#15) still has a
// `.default(null)` in the codegened Zod, so parsing fills the key back in as `null`. That is not
// coercion or loss — it normalizes an omitted optional to its explicit-null form — so it is the
// one shape of divergence this reconciler allows: a key `parsed` has that `original` lacks is
// fine only if Zod's value for it is `null`; anything else (added non-null data, changed values,
// a key `original` has that `parsed` lacks) still fails the comparison below.
function reconcileDefaultedNulls(parsed: unknown, original: unknown): unknown {
  if (Array.isArray(original) && Array.isArray(parsed)) {
    return parsed.map((p, i) => reconcileDefaultedNulls(p, original[i]));
  }
  if (
    original !== null &&
    typeof original === "object" &&
    parsed !== null &&
    typeof parsed === "object" &&
    !Array.isArray(parsed)
  ) {
    const originalObj = original as Record<string, unknown>;
    const result: Record<string, unknown> = {};
    for (const [key, value] of Object.entries(parsed as Record<string, unknown>)) {
      if (!(key in originalObj)) {
        if (value !== null) return parsed; // real loss/coercion — let the outer toEqual catch it
        continue; // an omitted optional, defaulted back to null — expected, not a divergence
      }
      result[key] = reconcileDefaultedNulls(value, originalObj[key]);
    }
    return result;
  }
  return parsed;
}

describe("Demo Document Python↔TS round-trip", () => {
  it.each(FIXTURES)("%s validates against the codegened Zod", (name) => {
    const doc = loadFixture(name);
    expect(() => demoDocumentSchema.parse(doc)).not.toThrow();
  });

  it.each(FIXTURES)("%s survives parse with no coercion or loss", (name) => {
    const doc = loadFixture(name);
    // Parsing applies Zod defaults but must not alter a fully-specified Python document:
    // parsed value === input === what Python re-validates, modulo an omitted optional field
    // (e.g. AssetRef.rights when unset) being filled back in as its explicit-null default —
    // see reconcileDefaultedNulls above.
    const parsed = demoDocumentSchema.parse(doc);
    expect(reconcileDefaultedNulls(parsed, doc)).toEqual(doc);
  });

  it("rejects a document that violates the schema", () => {
    const doc = loadFixture("minimal-demo.json") as {
      sections: { steps: { timing: { durationMs: unknown } }[] }[];
    };
    // durationMs must be a non-negative integer; a string is not coercible under strict Zod.
    doc.sections[0].steps[0].timing.durationMs = "soon";
    expect(demoDocumentSchema.safeParse(doc).success).toBe(false);
  });

  it("rejects an unknown cue type (the cue union is closed)", () => {
    const doc = loadFixture("full-demo.json") as {
      tracks: { cues: { type: string }[] };
    };
    doc.tracks.cues[0].type = "glow"; // not one of the five proven cue types
    expect(demoDocumentSchema.safeParse(doc).success).toBe(false);
  });
});
