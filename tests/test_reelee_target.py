"""Tests for the reelee RenderTarget: the timeline→PanelView mapping and the render driver.

The pure mapping is exercised directly; the render path is exercised with a *stub* film renderer
(and stub audio assembler) so no ffmpeg/MoviePy stack is needed — only ``reelee`` (for the
``PanelView`` shape) and ``burns`` (the pure pan/zoom path builder) must import.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

pytest.importorskip("reelee")
pytest.importorskip("burns")

from walkthru.core.schema import (  # noqa: E402
    Anchor,
    AssetRef,
    Beat,
    CameraKeyframe,
    Command,
    CommandStep,
    DemoDocument,
    NarrationAnchor,
    NarrationSegment,
    Section,
    Timing,
    Tracks,
)
from walkthru.core.timeline import resolve_timeline  # noqa: E402
from walkthru.ecosystem.reelee import (  # noqa: E402
    ReeleeRenderTarget,
    default_asset_resolver,
    render_demo_video,
    render_plans,
    timeline_to_panels,
    timeline_to_plans,
)
from walkthru.ports import RenderTarget  # noqa: E402


def _poster(tmp_path: Path, name: str) -> AssetRef:
    """A poster AssetRef whose uri points at a real (empty) file, so it resolves."""
    p = tmp_path / name
    p.write_bytes(b"\x89PNG")  # contents never read — film_renderer is stubbed
    return AssetRef(uri=str(p), mime="image/png")


def _demo(tmp_path: Path, *, with_audio: bool = False) -> DemoDocument:
    """Two command steps + a beat, posters that resolve, narration on step-1."""
    audio_ref = None
    if with_audio:
        a = tmp_path / "narr-1.wav"
        a.write_bytes(b"RIFF")
        audio_ref = AssetRef(uri=str(a), mime="audio/wav")
    return DemoDocument(
        id="demo-reelee",
        sections=[
            Section(
                id="s1",
                steps=[
                    CommandStep(
                        id="step-1",
                        command=Command(id="doc.edit"),
                        timing=Timing(duration_ms=3000, hold_after_ms=500),
                        poster=_poster(tmp_path, "step-1.png"),
                    ),
                    Beat(
                        id="beat-1",
                        beat_kind="textCard",
                        timing=Timing(duration_ms=4000),
                        text="An interlude.",
                        poster=_poster(tmp_path, "beat-1.png"),
                    ),
                    CommandStep(
                        id="step-2",
                        command=Command(id="doc.save"),
                        timing=Timing(duration_ms=2000),
                        poster=_poster(tmp_path, "step-2.png"),
                    ),
                ],
            )
        ],
        tracks=Tracks(
            narration=[
                NarrationSegment(
                    id="n1",
                    text="First, type some text.",
                    anchor=NarrationAnchor(step_id="step-1", duration_ms=3000),
                    audio_ref=audio_ref,
                ),
            ],
            camera=[
                CameraKeyframe(id="cam-1", anchor=Anchor(step_id="step-2"), zoom=1.5),
            ],
        ),
    )


# --------------------------------------------------------------------------------------
# The mapping
# --------------------------------------------------------------------------------------


def test_timeline_to_panels_maps_each_step_in_order(tmp_path):
    panels = timeline_to_panels(resolve_timeline(_demo(tmp_path)))
    assert [p.panel_id for p in panels] == ["step-1", "beat-1", "step-2"]
    assert [p.index for p in panels] == [1, 2, 3]
    # caption: narration text on step-1; the beat falls back to its own text; step-2 has neither
    assert panels[0].caption == "First, type some text."
    assert panels[1].caption == "An interlude."
    assert panels[2].caption == ""
    # provenance notes + camera hint from the camera track (zoom 1.5 -> push in)
    assert panels[0].notes == "command: doc.edit"
    assert panels[1].notes == "beat: textCard"
    assert panels[2].camera == "push in"
    # posters resolve to local files
    assert all(p.image_path is not None for p in panels)


def test_unresolved_poster_yields_no_image(tmp_path):
    doc = _demo(tmp_path)
    # A resolver that never resolves -> every panel image is None
    panels = timeline_to_panels(resolve_timeline(doc), poster_resolver=lambda _ref: None)
    assert all(p.image_path is None for p in panels)


def test_plans_carry_timeline_duration_and_audio(tmp_path):
    plans = timeline_to_plans(resolve_timeline(_demo(tmp_path, with_audio=True)))
    # step-1 occupancy = duration 3000 + hold 500 = 3.5s; beat = 4s; step-2 = 2s
    assert [round(p.duration_s, 3) for p in plans] == [3.5, 4.0, 2.0]
    # narration audio resolves only for step-1
    assert plans[0].audio_path is not None
    assert plans[1].audio_path is None and plans[2].audio_path is None


def test_plans_floor_short_steps_at_min_duration(tmp_path):
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(
                        id="quick",
                        command=Command(id="x"),
                        timing=Timing(duration_ms=200),
                        poster=_poster(tmp_path, "q.png"),
                    )
                ],
            )
        ],
    )
    plans = timeline_to_plans(resolve_timeline(doc), min_duration_s=2.0)
    assert plans[0].duration_s == 2.0  # 0.2s floored to the 2s minimum


def test_default_asset_resolver_existence(tmp_path):
    real = _poster(tmp_path, "real.png")
    missing = AssetRef(uri=str(tmp_path / "nope.png"))
    assert default_asset_resolver(real) == Path(real.uri)
    assert default_asset_resolver(missing) is None
    assert default_asset_resolver(None) is None


# --------------------------------------------------------------------------------------
# The render driver (stubbed film renderer)
# --------------------------------------------------------------------------------------


class _StubFilm:
    """Records the film_renderer call instead of invoking ffmpeg."""

    def __init__(self):
        self.calls = []

    def __call__(self, panels, *, saveas, fps, audio_path):
        self.calls.append(
            {"panels": list(panels), "fps": fps, "audio_path": audio_path}
        )
        Path(saveas).write_bytes(b"mp4")
        return Path(saveas)


def test_render_plans_drives_film_renderer(tmp_path):
    film = _StubFilm()
    out = tmp_path / "out.mp4"
    result = render_demo_video(_demo(tmp_path), out, fps=24, film_renderer=film)
    assert result == out and out.exists()
    assert len(film.calls) == 1
    call = film.calls[0]
    assert call["fps"] == 24
    assert call["audio_path"] is None  # no narration audio in this demo
    # one (image, BurnsPath, duration) panel per step, durations from the timeline
    assert [round(p[2], 3) for p in call["panels"]] == [3.5, 4.0, 2.0]
    assert all(isinstance(p[0], Path) for p in call["panels"])


def test_render_assembles_audio_when_narration_present(tmp_path):
    film = _StubFilm()
    assembled = {}

    def stub_assembler(segments, *, output):
        assembled["segments"] = list(segments)
        Path(output).write_bytes(b"wav")
        return Path(output)

    render_demo_video(
        _demo(tmp_path, with_audio=True),
        tmp_path / "out.mp4",
        film_renderer=film,
        audio_assembler=stub_assembler,
    )
    assert "segments" in assembled  # assembler ran because step-1 has audio
    assert film.calls[0]["audio_path"] is not None


def test_render_raises_without_any_image(tmp_path):
    doc = DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(
                        id="step-1",
                        command=Command(id="x"),
                        timing=Timing(duration_ms=1000),
                    )
                ],
            )
        ],
    )  # no posters at all
    with pytest.raises(ValueError, match="no panel has a resolvable poster"):
        render_plans(timeline_to_plans(resolve_timeline(doc)), tmp_path / "o.mp4")


# --------------------------------------------------------------------------------------
# The port adapter
# --------------------------------------------------------------------------------------


def test_render_target_satisfies_port(tmp_path):
    assert isinstance(ReeleeRenderTarget(tmp_path), RenderTarget)


def test_export_writes_mp4_and_returns_assetref(tmp_path):
    film = _StubFilm()
    target = ReeleeRenderTarget(tmp_path, fps=30, film_renderer=film)
    ref = asyncio.run(target.export(_demo(tmp_path)))
    expected = tmp_path / "demo-reelee.mp4"
    assert ref.uri == str(expected) and ref.mime == "video/mp4"
    assert expected.exists()
    assert len(film.calls) == 1
