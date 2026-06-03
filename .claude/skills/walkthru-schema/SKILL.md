---
name: walkthru-schema
description: >-
  The exact, ordered workflow for changing walkthru's Demo Document data model
  across the Python↔TypeScript seam. Use whenever you add/remove/rename a field,
  add a new step kind or cue type, change a default, or otherwise touch
  `walkthru/core/schema.py` — and whenever CI fails with a "schema is stale",
  "committed JSON schema out of date", codegen `--check`, or roundtrip/fixture
  mismatch error. The Pydantic models are the single source of truth; the JSON
  Schema, the TS Zod, and the fixtures are all generated/derived and guarded by
  tests that fail together if you skip a step. Trigger even if the user just says
  "add a field to the demo document", "the Zod is out of sync", or "regenerate
  the schema".
---

# Changing the Demo Document schema

`walkthru/core/schema.py` (Pydantic v2) is the **single source of truth** for the
whole data model. Three things are derived from it and **must not be hand-edited**:

- `schema/demo-document.schema.json` — the published JSON Schema (camelCase).
- `ts/src/schema.generated.ts` — the Zod schema + `DemoDocument` TS type.
- The cross-language fixtures in `schema/fixtures/` (mirrored by `tests/builders.py`).

Four guard tests fail *together* if these drift, so the only safe way to change
the model is to regenerate everything in order. Skipping a step doesn't produce a
subtle bug — it produces a red CI you'll have to come back and fix.

## The workflow (do these in order)

### 1. Edit the Pydantic models in `walkthru/core/schema.py`

Honor the conventions baked into the schema, or the round-trip won't be lossless:

- **camelCase on the wire.** Models inherit a base that aliases snake_case →
  camelCase automatically. Just name fields snake_case; don't add manual aliases.
- **Relative time only.** Durations are `*_ms` integers (`duration_ms`,
  `hold_after_ms`, `local_offset_ms`, `hold_ms`). Never introduce an absolute
  timestamp — `test_no_absolute_time_in_schema` greps the emitted schema for the
  substring `timestamp` and fails.
- **Anchors, not back-references.** Cues/narration/camera attach to steps via an
  anchor (`{stepId, localOffsetMs}`) in the parallel `tracks`, not via fields on
  the step. Keep new annotation types anchor-based.
- **Discriminated unions** key off a literal field. A new step kind extends the
  `Step` union (discriminant `kind`); a new cue extends the `Cue` union
  (discriminant `type`). The TS codegen realizes these as closed unions that
  *reject* unknown variants — so adding one is a real schema change, not additive.

### 2. Regenerate the committed JSON Schema

The command is documented in `demo_document_json_schema`'s docstring:

```bash
python -c "import json, walkthru.core.schema as s; \
print(json.dumps(s.demo_document_json_schema(), indent=2))" \
  > schema/demo-document.schema.json
```

Guard: `tests/test_schema.py::test_committed_json_schema_is_up_to_date` asserts
the file on disk equals what Pydantic emits.

### 3. Regenerate the TypeScript Zod

```bash
cd ts && npm run codegen      # writes ts/src/schema.generated.ts from the JSON Schema
```

`codegen.mjs` dereferences all `$ref`s (Pydantic emits nested models as `$defs`,
which `json-schema-to-zod` won't inline on its own), then emits Zod v4. Guard:
`ts/src/schema.codegen.test.ts` runs `codegen.mjs --check` and fails if the
committed file is stale. **Never edit `schema.generated.ts` by hand** — it carries
a "GENERATED … do not edit" header and your changes will be overwritten.

### 4. Update the builders and fixtures (only if shapes changed)

`tests/builders.py` hand-authors the canonical documents; `schema/fixtures/*.json`
are their committed JSON projections and are the exact bytes the TS round-trip
test parses. If your change alters what a fixture should contain:

1. Update the relevant builder in `tests/builders.py`
   (`make_minimal_demo` / `make_rich_demo` / `make_full_demo`).
2. Regenerate the affected fixture from its builder, e.g.:

```bash
python -c "from tests.builders import make_full_demo; \
print(make_full_demo().model_dump_json(by_alias=True, indent=2))" \
  > schema/fixtures/full-demo.json
```

Guards: `test_committed_fixture_validates_and_matches_builder` (Python: fixture
re-parses to exactly the builder's document) and `schema.roundtrip.test.ts` (TS:
each fixture validates under the codegened Zod with **no** loss/coercion). If you
add a new step kind or cue type, extend `make_full_demo` so the union variant is
actually exercised on both sides.

### 5. Export new public symbols

If you added a user-facing model, re-export it from `walkthru/__init__.py` — it's
the documented API surface.

### 6. Run both suites

```bash
pytest tests/test_schema.py -v
cd ts && npm test
```

Green on both means the seam is consistent end to end.

## Why this many guards?

The whole value proposition is "owns the representation": a `DemoDocument` written
by the Python side must be byte-faithfully understood by the TS side and any
renderer. The guards turn "someone forgot to regenerate" from a silent
cross-language data bug into an immediate, local test failure. When several of
them go red at once after a schema edit, that's expected — walk steps 2→6 in order
and they'll clear together.

## Quick checklist

- [ ] Edited `walkthru/core/schema.py` (camelCase-aliased, relative-time, anchor-based)
- [ ] Regenerated `schema/demo-document.schema.json`
- [ ] Ran `npm run codegen` (regenerated `ts/src/schema.generated.ts`)
- [ ] Updated builders + regenerated affected `schema/fixtures/*.json`
- [ ] Re-exported any new public symbol from `walkthru/__init__.py`
- [ ] `pytest` and `cd ts && npm test` both green
