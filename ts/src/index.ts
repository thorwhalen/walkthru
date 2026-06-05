/**
 * acture-walkthru — the TypeScript surface of walkthru.
 *
 * walkthru represents a demo/tour as an editable *Demo Document*. This package
 * exposes that contract on the TS side: a Zod schema generated from the Python
 * Pydantic single source of truth (`walkthru/core/schema.py`) plus its inferred
 * TypeScript type. A document produced anywhere — Python, a renderer, a capture
 * tool — can therefore be validated and typed identically in TypeScript.
 *
 * The live capture/play engine (over `acture`) lands in a later stage; for now
 * the package is the schema seam.
 */
export { demoDocumentSchema } from "./schema.generated.js";
export type { DemoDocument } from "./schema.generated.js";
