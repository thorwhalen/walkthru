"""Schema tests: JSON round-trip, camelCase wire format, and the published JSON Schema."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from walkthru.core.schema import DemoDocument, demo_document_json_schema

from tests.builders import make_minimal_demo, make_rich_demo

ROOT = Path(__file__).resolve().parents[1]
SCHEMA_FILE = ROOT / "schema" / "demo-document.schema.json"
FIXTURE_FILE = ROOT / "schema" / "fixtures" / "minimal-demo.json"


@pytest.mark.parametrize("make", [make_minimal_demo, make_rich_demo])
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


def test_committed_fixture_validates_and_matches_builder():
    assert FIXTURE_FILE.exists(), f"missing {FIXTURE_FILE}"
    doc = DemoDocument.model_validate_json(FIXTURE_FILE.read_text())
    assert doc == make_minimal_demo()


def test_fixture_validates_against_json_schema():
    """Validate the fixture against the emitted JSON Schema (skipped if jsonschema absent)."""
    jsonschema = pytest.importorskip("jsonschema")
    instance = json.loads(FIXTURE_FILE.read_text())
    jsonschema.validate(instance=instance, schema=demo_document_json_schema())
