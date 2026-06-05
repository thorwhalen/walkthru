import { describe, it, expect } from "vitest";
import { demoDocumentSchema } from "./index.js";

// Smoke-tests the *public entry point*: that the generated schema is actually
// re-exported and usable. The exhaustive Python↔TS round-trip lives in
// schema.roundtrip.test.ts; this just guards the package's public surface.
describe("public entry", () => {
  it("re-exports the Demo Document schema", () => {
    expect(demoDocumentSchema).toBeDefined();
    expect(typeof demoDocumentSchema.parse).toBe("function");
  });

  it("validates a minimal Demo Document", () => {
    const doc = {
      id: "demo-minimal",
      sections: [
        {
          id: "s1",
          steps: [
            {
              kind: "command",
              id: "step-1",
              command: { id: "app.open" },
              timing: { durationMs: 500 },
            },
          ],
        },
      ],
    };
    expect(() => demoDocumentSchema.parse(doc)).not.toThrow();
  });

  it("rejects an unknown step kind (closed union)", () => {
    const bad = {
      id: "demo-bad",
      sections: [{ id: "s1", steps: [{ kind: "teleport", id: "x" }] }],
    };
    expect(() => demoDocumentSchema.parse(bad)).toThrow();
  });
});
