"""Guards for ``AssetRights`` — the rights/attribution record carried on ``AssetRef``.

This mirrors the illustration package's ``RIGHTS_FIELDS`` (its SSOT for the fields that answer
"may we ship this, and whom must we credit?"), by name, so a producer that already holds an
``ImageResult``-shaped record can populate ``AssetRights`` one-for-one. See
``thorwhalen/illustration#15`` (the consumer this field was added for) and ``thorwhalen/walkthru#32``.
"""

from __future__ import annotations

import json

from walkthru.core.schema import (
    AssetRef,
    AssetRights,
    Beat,
    DemoDocument,
    Section,
    Timing,
)

#: Literal pin, deliberately hand-written rather than derived: a trim here is a decision, not an
#: accident. Mirrors ``illustration.schema.RIGHTS_FIELDS`` exactly — same names, same order.
RIGHTS_FIELDS = (
    "license",
    "license_url",
    "attribution",
    "source_page_url",
    "author",
    "author_url",
    "cacheable",
)


def test_asset_rights_field_names_are_pinned():
    """A dropped or renamed field here silently breaks a consumer populating by name."""
    assert tuple(AssetRights.model_fields) == RIGHTS_FIELDS


def test_asset_ref_carries_an_optional_rights_slot():
    assert "rights" in AssetRef.model_fields
    assert AssetRef.model_fields["rights"].default is None


def test_every_rights_field_survives_a_round_trip():
    """Every ``RIGHTS_FIELDS`` value set on an ``AssetRights`` reaches the wire and back unchanged."""
    rights = AssetRights(
        license="cc-by-4.0",
        license_url="https://creativecommons.org/licenses/by/4.0/",
        attribution="Photo by Jane Doe",
        source_page_url="https://example.com/photos/beat-1",
        author="Jane Doe",
        author_url="https://example.com/authors/jane-doe",
        cacheable=True,
    )
    ref = AssetRef(uri="assets/beat-1.png", mime="image/png", rights=rights)
    round_tripped = AssetRef.model_validate_json(ref.model_dump_json(by_alias=True))

    for field in RIGHTS_FIELDS:
        assert getattr(round_tripped.rights, field) == getattr(rights, field)

    # And the wire form uses the camelCase alias for each multi-word field.
    wire = json.loads(ref.model_dump_json(by_alias=True))
    assert wire["rights"]["licenseUrl"] == rights.license_url
    assert wire["rights"]["sourcePageUrl"] == rights.source_page_url
    assert wire["rights"]["authorUrl"] == rights.author_url


def test_cacheable_none_is_distinguishable_from_false():
    """``cacheable`` is ``bool | None``: "not recorded" must not collapse into "not cacheable"."""
    not_recorded = AssetRights()
    recorded_false = AssetRights(cacheable=False)
    assert not_recorded.cacheable is None
    assert recorded_false.cacheable is False


def test_a_document_with_no_rights_data_omits_the_field_as_null():
    """An asset with no rights record round-trips with ``rights: null`` — not an error, not a stub."""
    doc = DemoDocument(
        id="demo",
        sections=[
            Section(
                id="s1",
                steps=[
                    Beat(
                        id="beat-1",
                        beat_kind="broll",
                        timing=Timing(duration_ms=100),
                        poster=AssetRef(uri="assets/beat-1.png"),
                    )
                ],
            )
        ],
    )
    wire = json.loads(doc.model_dump_json(by_alias=True))
    assert wire["sections"][0]["steps"][0]["poster"]["rights"] is None


def test_pre_existing_documents_without_a_rights_key_still_load():
    """Backward compatibility: a Demo Document persisted before this field existed still parses.

    ``AssetRef`` keeps ``extra="forbid"``; the new field is purely additive (optional, default
    ``None``), so an on-disk document written by an older walkthru — with no ``rights`` key at
    all in its ``poster``/``audioRef`` objects — must still validate.
    """
    old_style_json = json.dumps(
        {
            "id": "demo",
            "sections": [
                {
                    "id": "s1",
                    "steps": [
                        {
                            "kind": "beat",
                            "id": "beat-1",
                            "beatKind": "broll",
                            "timing": {"durationMs": 100},
                            "poster": {"uri": "assets/beat-1.png", "mime": "image/png"},
                        }
                    ],
                }
            ],
        }
    )
    doc = DemoDocument.model_validate_json(old_style_json)
    assert doc.sections[0].steps[0].poster.rights is None
