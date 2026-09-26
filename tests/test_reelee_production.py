"""Tests for the camera-driven motion and the commentary-production manifest.

``camera_move`` / ``normalized_focus`` / ``to_production_manifest`` are pure (media probes are
injected), so they run wherever ``reelee`` imports. ``camera_path_builder`` frames against a real
image, so it needs ``burns`` and Pillow; the film renderer is never called.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytest.importorskip("reelee")
pytest.importorskip("burns")

from walkthru.core.schema import (  # noqa: E402
    Anchor,
    AssetRef,
    CameraKeyframe,
    Command,
    CommandStep,
    DemoDocument,
    NarrationAnchor,
    NarrationSegment,
    Rect,
    Section,
    Timing,
    Tracks,
)
from walkthru.core.timeline import resolve_timeline  # noqa: E402
from walkthru.ecosystem.reelee import (  # noqa: E402
    CameraMove,
    FootageTrack,
    Framing,
    camera_path_builder,
    normalized_focus,
    render_plans,
    timeline_to_plans,
    to_production_manifest,
)

SIZE = (1920, 1080)


def _doc(tmp_path: Path, *, image_bytes: bytes = b"\x89PNG") -> DemoDocument:
    """Three steps: push onto a rect, pull out, and one with no camera keyframe."""

    def step(sid: str, ms: int) -> CommandStep:
        poster = tmp_path / f"{sid}.png"
        poster.write_bytes(image_bytes)
        return CommandStep(
            id=sid,
            command=Command(id="x"),
            timing=Timing(duration_ms=ms, hold_after_ms=500),
            poster=AssetRef(uri=str(poster)),
        )

    audio = tmp_path / "a.mp3"
    audio.write_bytes(b"ID3")
    return DemoDocument(
        id="d",
        sections=[
            Section(id="s", steps=[step("a", 3000), step("b", 2500), step("c", 2000)])
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n",
                    text="Look at this.",
                    anchor=NarrationAnchor(step_id="b", duration_ms=2000),
                    audio_ref=AssetRef(uri=str(audio)),
                )
            ],
            camera=[
                CameraKeyframe(
                    id="ca",
                    anchor=Anchor(step_id="a"),
                    zoom=1.5,
                    focus=Rect(x=480, y=270, width=960, height=540),
                ),
                CameraKeyframe(id="cb", anchor=Anchor(step_id="b"), zoom=0.8),
            ],
        ),
    )


def _plans(tmp_path, **kw):
    return timeline_to_plans(resolve_timeline(_doc(tmp_path, **kw)))


def test_plans_carry_the_camera_track_as_named_moves(tmp_path):
    a, b, c = _plans(tmp_path)
    assert a.move == CameraMove(
        move="push_in", zoom=1.5, focus=Rect(x=480, y=270, width=960, height=540)
    )
    assert (b.move.move, round(b.move.zoom, 3), b.move.focus) == (
        "pull_out",
        1.25,
        None,
    )
    assert c.move is None  # no keyframe: the path builder's default decides


def test_normalized_focus_scales_and_clamps():
    assert normalized_focus(Rect(x=480, y=270, width=960, height=540), SIZE) == (
        0.25,
        0.25,
        0.5,
        0.5,
    )
    # a retina capture: CSS pixels are half the image's
    assert normalized_focus(
        Rect(x=480, y=270, width=960, height=540), (3840, 2160), device_scale_factor=2.0
    ) == (0.25, 0.25, 0.5, 0.5)
    # an element scrolled half out of view is clipped to what the picture shows
    x, y, w, h = normalized_focus(Rect(x=-100, y=900, width=400, height=400), SIZE)
    assert (x, y) == (0.0, 900 / 1080) and w == pytest.approx(300 / 1920)
    assert y + h == pytest.approx(1.0)


def test_camera_path_builder_frames_on_the_focus(tmp_path):
    """The push-in ends on the focus rect; the default-move panel holds the whole frame."""
    Image = pytest.importorskip("PIL.Image")
    import io

    buf = io.BytesIO()
    Image.new("RGB", SIZE, (40, 40, 40)).save(buf, format="PNG")
    a, _b, c = _plans(tmp_path, image_bytes=buf.getvalue())
    build = camera_path_builder(Framing(aspect=16 / 9))
    path = build(a)
    end = path.evaluate(1.0)  # a Rect in the image's normalized frame
    cx, cy = end.x + end.w / 2, end.y + end.h / 2
    assert cx == pytest.approx(0.5, abs=0.02) and cy == pytest.approx(0.5, abs=0.02)
    assert end.w < path.evaluate(0.0).w  # it did push in
    held = build(c)
    assert held.evaluate(0.0) == held.evaluate(1.0)  # default move: hold still


def test_render_plans_uses_the_injected_path_builder_and_keeps_the_audio(tmp_path):
    calls = {}

    def film(panels, *, saveas, fps, audio_path):
        calls["paths"] = [p[1] for p in panels]
        calls["audio"] = audio_path
        Path(saveas).write_bytes(b"mp4")

    def assembler(segments, *, output):
        Path(output).write_bytes(b"wav")
        return Path(output)

    keep = tmp_path / "keep" / "recording.wav"
    render_plans(
        _plans(tmp_path),
        tmp_path / "f.mp4",
        film_renderer=film,
        audio_assembler=assembler,
        path_builder=lambda plan: plan.view.panel_id,
        audio_out=keep,
    )
    assert calls["paths"] == ["a", "b", "c"]
    assert calls["audio"] == keep and keep.exists()  # not a vanished temp file


def test_manifest_lays_panels_and_beats_out_as_the_film_does(tmp_path):
    film, audio = tmp_path / "film.mp4", tmp_path / "rec.wav"
    film.write_bytes(b"mp4")
    audio.write_bytes(b"wav")
    m = to_production_manifest(
        _plans(tmp_path),
        production="demo",
        title="Demo",
        source_dir=tmp_path,
        film=film,
        audio=audio,
        rights={"position": "private", "why": "a test"},
        fps=30,
        voice={"voice_id": "v", "model_id": "m"},
        duration_s=lambda p: 1.5 if p.suffix == ".mp3" else 9.0,
        image_size=lambda p: SIZE,
        film_size=lambda first, aspect: first,
    )
    assert m["moves"] == "rendered" and m["source_dir"] == "."
    cut = m["cuts"][0]
    panels = cut["panels"]
    # screen time is duration + hold, laid end to end from 0
    assert [(p["start"], p["end"]) for p in panels] == [
        (0, 3.5),
        (3.5, 6.5),
        (6.5, 9.0),
    ]
    assert [p["move"] for p in panels] == ["push_in", "pull_out", "hold"]
    assert panels[0]["focus"] == {"x": 0.25, "y": 0.25, "w": 0.5, "h": 0.5}
    assert panels[1]["zoom"] == 1.25
    # the one narration beat starts with its panel and lasts as long as its take
    (beat,) = cut["beats"]
    assert (beat["start"], beat["end"], beat["text"]) == (3.5, 5.0, "Look at this.")
    assert beat["take"] == {
        "path": "a.mp3",
        "duration_s": 1.5,
        "source": "tts",
        "voice_id": "v",
        "model_id": "m",
    }
    assert [s["path"] for s in m["stills"]] == ["a.png", "b.png", "c.png"]
    assert cut["duration_s"] == 9.0 and cut["artifact"] == "film.mp4"


def test_manifest_refuses_a_file_outside_the_source_dir(tmp_path):
    inside = tmp_path / "prod"
    inside.mkdir()
    with pytest.raises(ValueError, match="not under the production's source_dir"):
        to_production_manifest(
            _plans(tmp_path),  # posters sit in tmp_path, outside `inside`
            production="demo",
            title="Demo",
            source_dir=inside,
            film=inside / "f.mp4",
            audio=inside / "r.wav",
            rights={"position": "private", "why": "a test"},
            fps=30,
            duration_s=lambda p: 1.0,
            image_size=lambda p: SIZE,
            film_size=lambda first, aspect: first,
        )


def test_manifest_validates_against_braidio_when_it_is_installed(tmp_path):
    """The dict is braidio's wire shape: its own loader accepts it."""
    importing = pytest.importorskip("braidio.importing")
    if "moves" not in importing.ProductionManifest.model_fields:
        pytest.skip("this braidio predates ProductionManifest.moves")
    film, audio = tmp_path / "film.mp4", tmp_path / "rec.wav"
    film.write_bytes(b"mp4")
    audio.write_bytes(b"wav")
    m = to_production_manifest(
        _plans(tmp_path),
        production="demo",
        title="Demo",
        source_dir=tmp_path,
        film=film,
        audio=audio,
        rights={"position": "private", "why": "a test"},
        fps=30,
        duration_s=lambda p: 1.0,
        image_size=lambda p: SIZE,
        film_size=lambda first, aspect: first,
    )
    manifest = importing.ProductionManifest.model_validate(m)
    assert manifest.moves == "rendered"


def _manifest(tmp_path, plans, **kw):
    film, audio = tmp_path / "film.mp4", tmp_path / "rec.wav"
    film.write_bytes(b"mp4")
    audio.write_bytes(b"wav")
    return to_production_manifest(
        plans,
        production="demo",
        title="Demo",
        source_dir=tmp_path,
        film=film,
        audio=audio,
        rights={"position": "private", "why": "a test"},
        fps=30,
        duration_s=lambda p: 1.0,
        image_size=lambda p: SIZE,
        **kw,
    )


def test_manifest_refuses_an_easing_no_panel_record_can_carry(tmp_path):
    with pytest.raises(ValueError, match="carries no easing"):
        _manifest(tmp_path, _plans(tmp_path), framing=Framing(easing="linear"))


def test_manifest_takes_the_film_size_from_the_first_picture_like_burns(tmp_path):
    """A retina capture makes a 3840x2160 film; the record must not say 1920x1080."""
    m = _manifest(
        tmp_path,
        _plans(tmp_path),
        framing=Framing(aspect=16 / 9),
        film_size=lambda first, aspect: (first[0] * 2, first[1] * 2),
    )
    assert (m["cuts"][0]["width"], m["cuts"][0]["height"]) == (3840, 2160)


def test_a_zero_zoom_keyframe_names_no_move(tmp_path):
    doc = _doc(tmp_path)
    doc.tracks.camera[1].zoom = 0.0
    _a, b, _c = timeline_to_plans(resolve_timeline(doc))
    assert b.move is None  # no ZeroDivisionError on any path; the default decides


# --- a film cut from a screen recording ------------------------------------------------


def _footage(tmp_path, **kw):
    rec = tmp_path / "screen.mp4"
    rec.write_bytes(b"mp4")
    return FootageTrack(
        path=rec,
        in_points={"a": 0.25, "b": 3.9, "c": 7.1},
        size=(1080, 1920),
        fps=30,
        **kw,
    )


def test_footage_panels_name_the_recording_and_hold_still(tmp_path):
    m = _manifest(
        tmp_path, _plans(tmp_path), footage=_footage(tmp_path), video_duration_s=lambda p: 12.5
    )
    cut = m["cuts"][0]
    assert [p["footage"] for p in cut["panels"]] == [
        {"key": "screencast", "in_s": 0.25},
        {"key": "screencast", "in_s": 3.9},
        {"key": "screencast", "in_s": 7.1},
    ]
    # no move is rendered over footage, and the records say so
    assert {(p["move"], p["zoom"], p["focus"]) for p in cut["panels"]} == {
        ("hold", 1.0, None)
    }
    # the film is the recording's size, not a picture's
    assert (cut["width"], cut["height"]) == (1080, 1920)
    assert m["footage"] == [
        {"key": "screencast", "path": "screen.mp4", "width": 1080, "height": 1920,
         "fps": 30, "duration_s": 12.5}
    ]
    # the spans are the narration's, exactly as for a Ken Burns film
    assert [(p["start"], p["end"]) for p in cut["panels"]] == [
        (0, 3.5), (3.5, 6.5), (6.5, 9.0)
    ]


def test_footage_needs_an_in_point_for_every_panel(tmp_path):
    from dataclasses import replace

    track = replace(_footage(tmp_path), in_points={"a": 0.0})
    with pytest.raises(ValueError, match=r"no in-point for panels \['b', 'c'\]"):
        _manifest(tmp_path, _plans(tmp_path), footage=track)


def test_footage_ignores_an_easing_it_never_renders(tmp_path):
    m = _manifest(
        tmp_path, _plans(tmp_path), framing=Framing(easing="linear"),
        footage=_footage(tmp_path), video_duration_s=lambda p: 12.5,
    )
    assert m["cuts"][0]["panels"][0]["move"] == "hold"


def test_a_footage_manifest_validates_against_braidio_when_it_can(tmp_path):
    importing = pytest.importorskip("braidio.importing")
    if "footage" not in importing.ProductionManifest.model_fields:
        pytest.skip("this braidio predates footage panels")
    m = _manifest(
        tmp_path, _plans(tmp_path), footage=_footage(tmp_path), video_duration_s=lambda p: 12.5
    )
    manifest = importing.ProductionManifest.model_validate(m)
    assert manifest.footage_keys == {"screencast"}
    assert manifest.cuts[0].panels[1].footage.in_s == 3.9


def test_an_in_point_past_the_recording_is_refused(tmp_path):
    with pytest.raises(ValueError, match=r"past the end of the 5.00s recording: \{'c': 7.1\}"):
        _manifest(
            tmp_path, _plans(tmp_path), footage=_footage(tmp_path), video_duration_s=lambda p: 5.0
        )
