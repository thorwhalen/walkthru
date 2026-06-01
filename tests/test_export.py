"""Export tests: the JSON artifact hand-off and WebVTT narration captions."""

from __future__ import annotations

import asyncio
import json

from walkthru.adapters.export import JsonArtifactTarget, narration_to_webvtt, to_json
from walkthru.core.schema import AssetRef, DemoDocument

from tests.builders import make_full_demo, make_minimal_demo


def test_to_json_is_validated_camelcase_projection():
    doc = make_full_demo()
    data = json.loads(to_json(doc))
    # camelCase wire keys, and it re-parses to the same document.
    assert "holdAfterMs" in data["sections"][0]["steps"][0]["timing"]
    assert DemoDocument.model_validate(data) == doc


def test_json_artifact_target_writes_roundtrippable_file(tmp_path):
    doc = make_minimal_demo()
    target = JsonArtifactTarget(out_dir=tmp_path)
    ref = asyncio.run(target.export(doc))

    assert isinstance(ref, AssetRef)
    assert ref.mime == "application/json"
    written = (tmp_path / "demo-minimal.json").read_text()
    assert DemoDocument.model_validate_json(written) == doc
    assert ref.uri.endswith("demo-minimal.json")


def test_json_artifact_target_satisfies_render_target_port():
    from walkthru.ports import RenderTarget

    assert isinstance(JsonArtifactTarget(), RenderTarget)


def test_webvtt_has_header_and_derived_timings():
    vtt = narration_to_webvtt(make_full_demo())
    lines = vtt.splitlines()

    assert lines[0] == "WEBVTT"
    # narr-1 anchors to step-1 (start 0) for 1000ms -> 00:00:00.000 --> 00:00:01.000
    assert "00:00:00.000 --> 00:00:01.000" in lines
    assert "First, let's type some text." in lines
    assert vtt.endswith("\n")


def test_webvtt_is_empty_but_valid_without_narration():
    vtt = narration_to_webvtt(make_minimal_demo())
    assert vtt.startswith("WEBVTT")
    # no cues, but still a valid (empty) WebVTT document
    assert "-->" not in vtt


def test_webvtt_cues_are_time_ordered():
    """Two narration segments emit in ascending start time regardless of track order."""
    from walkthru.core.schema import (
        Command,
        CommandStep,
        NarrationAnchor,
        NarrationSegment,
        Section,
        Timing,
        Tracks,
    )

    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(
                        id="a", command=Command(id="x"), timing=Timing(duration_ms=1000)
                    ),
                    CommandStep(
                        id="b", command=Command(id="y"), timing=Timing(duration_ms=1000)
                    ),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n-late",
                    text="second",
                    anchor=NarrationAnchor(step_id="b", duration_ms=500),
                ),
                NarrationSegment(
                    id="n-early",
                    text="first",
                    anchor=NarrationAnchor(step_id="a", duration_ms=500),
                ),
            ]
        ),
    )
    vtt = narration_to_webvtt(doc)
    assert vtt.index("first") < vtt.index("second")
