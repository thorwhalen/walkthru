// Drift guard: the committed src/schema.generated.ts must match what codegen produces from the
// current schema/demo-document.schema.json. Paired with the Python-side guard
// (tests/test_schema.py::test_committed_json_schema_is_up_to_date, which pins the JSON Schema to
// the Pydantic SSOT), this chains the whole pipeline: edit a Pydantic model and forget to
// regenerate either artifact, and a test goes red.
//
// We invoke the real `codegen.mjs --check` CLI rather than importing it, so the script (plain JS
// with a runtime ref-parser dependency) never enters tsc's type-check graph for `src`.

import { execSync } from "node:child_process";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const TS_ROOT = resolve(dirname(fileURLToPath(import.meta.url)), "..");

describe("codegen drift guard", () => {
  it("committed schema.generated.ts is up to date with the JSON Schema", () => {
    const run = () =>
      execSync("node scripts/codegen.mjs --check", {
        cwd: TS_ROOT,
        encoding: "utf8",
        stdio: "pipe",
      });
    expect(run).not.toThrow();
  });
});
