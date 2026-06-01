"""Schema tests: JSON round-trip, camelCase wire format, and the published JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from walkthru.core.schema import DemoDocument, demo_document_json_schema

from tests.builders import make_full_demo, make_minimal_demo, make_rich_demo

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schema" / "demo-document.schema.json"
FIXTURE_DIR = ROOT / "schema" / "fixtures"
FIXTURE_FILE = FIXTURE_DIR / "minimal-demo.json"

#: Committed fixtures and the builder each must reproduce — the Python side of the cross-language
#: contract the TS round-trip test (``ts/src/schema.roundtrip.test.ts``) validates from.
FIXTURES = [
    (FIXTURE_DIR / "minimal-demo.json", make_minimal_demo),
    (FIXTURE_DIR / "full-demo.json", make_full_demo),
]


@pytest.mark.parametrize("make", [make_minimal_demo, make_rich_demo, make_full_demo])
def test_json_roundtrip_is_lossless(make):
    doc = make()
    wire = doc.model_dump_json(by_alias=True)
    again = DemoDocument.model_validate_json(wire)
    assert again == doc


def test_wire_format_is_camelcase():
    doc = make_minimal_demo()
    data = json.loads(doc.model_dump_json(by_alias=True))
    step = data["sections"][0]["steps"][1]
    # snake_case Python -> camelCase JSON
    assert "holdAfterMs" in step["timing"]
    assert "durationMs" in step["timing"]


def test_reserved_branching_seam_present_but_unused():
    """`next` exists in the schema (a seam) and defaults to null."""
    doc = make_minimal_demo()
    data = json.loads(doc.model_dump_json(by_alias=True))
    assert data["sections"][0]["steps"][0]["next"] is None


def test_no_absolute_time_in_schema():
    """The SSOT carries only relative *Ms durations — never an absolute timestamp."""
    schema_text = json.dumps(demo_document_json_schema())
    assert "timestamp" not in schema_text.lower()


def test_committed_json_schema_is_up_to_date():
    """The committed schema file must match what the Pydantic SSOT emits (regen guard)."""
    assert SCHEMA_FILE.exists(), f"missing {SCHEMA_FILE}; regenerate it (see schema.py)"
    on_disk = json.loads(SCHEMA_FILE.read_text())
    assert on_disk == demo_document_json_schema()


@pytest.mark.parametrize("fixture, make", FIXTURES)
def test_committed_fixture_validates_and_matches_builder(fixture, make):
    """Each committed fixture must re-parse to exactly its builder's document.

    This anchors the fixture the TS round-trip reads: if the fixture drifts from the SSOT, both
    this test and the TS ``schema.roundtrip`` test fail together.
    """
    assert fixture.exists(), f"missing {fixture}; regenerate from {make.__name__}()"
    doc = DemoDocument.model_validate_json(fixture.read_text())
    assert doc == make()


@pytest.mark.parametrize("fixture, make", FIXTURES)
def test_fixture_validates_against_json_schema(fixture, make):
    """Validate each fixture against the emitted JSON Schema (skipped if jsonschema absent)."""
    jsonschema = pytest.importorskip("jsonschema")
    instance = json.loads(fixture.read_text())
    jsonschema.validate(instance=instance, schema=demo_document_json_schema())
