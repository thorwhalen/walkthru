"""The GIF render target: pure geometry, the filtergraph, and the driver with a fake runner.

Everything that carries meaning is a pure function, so none of this needs ffmpeg.
"""

import asyncio
import json
import subprocess

import pytest

from walkthru.adapters.gif import (
    CameraSegment,
    FfmpegMissingError,
    GifRenderError,
    GifRenderTarget,
    VideoInfo,
    camera_segments,
    check_ffmpeg,
    crop_box,
    gif_filtergraph,
    probe_video,
    video_to_gif,
)
from walkthru.core.schema import (
    Anchor,
    CameraKeyframe,
    Command,
    CommandStep,
    DemoDocument,
    Rect,
    Section,
    Timing,
    Tracks,
)
from walkthru.core.timeline import Timeline, resolve_timeline


# ------------------------------------------------------------------ pure geometry

def test_no_keyframes_is_one_full_frame_segment():
    empty = Timeline(steps=(), cues=(), narration=(), camera=(), total_ms=0)
    assert camera_segments(empty, total_ms=5000) == (CameraSegment(0, 5000),)


def test_full_frame_crop_is_the_whole_frame():
    assert crop_box(None, 1.0, frame_w=1280, frame_h=720, aspect=16 / 9) == (0, 0, 1280, 720)


def test_zoom_crops_centrally():
    x, y, w, h = crop_box(None, 2.0, frame_w=1280, frame_h=720, aspect=16 / 9)
    assert (w, h) == (640, 360)
    assert (x + w / 2, y + h / 2) == (640, 360)  # still centred


def test_focus_rect_is_corrected_to_the_output_aspect():
    """A square focus in a 2:1 output must widen, not letterbox."""
    _, _, w, h = crop_box(
        Rect(x=100, y=100, width=100, height=100), 1.0,
        frame_w=1000, frame_h=1000, aspect=2.0,
    )
    assert w / h == pytest.approx(2.0)


def test_a_crop_never_leaves_the_frame():
    """A focus at the very edge is pulled inside rather than sampling nothing."""
    x, y, w, h = crop_box(
        Rect(x=980, y=980, width=40, height=40), 1.0,
        frame_w=1000, frame_h=1000, aspect=1.0,
    )
    assert x >= 0 and y >= 0 and x + w <= 1000 and y + h <= 1000


def test_crop_dimensions_are_even():
    """Odd dimensions break several encoders."""
    for zoom in (1.0, 1.3, 1.7, 2.9):
        _, _, w, h = crop_box(None, zoom, frame_w=1281, frame_h=721, aspect=16 / 9)
        assert w % 2 == 0 and h % 2 == 0, zoom


def test_short_segments_are_dropped():
    """Below a few frames a cut reads as a glitch."""
    doc = _doc_with_camera([(0, 1.0), (10, 2.0), (2000, 1.0)])
    segments = camera_segments(resolve_timeline(doc), total_ms=4000, min_segment_ms=80)
    assert all(s.duration_ms >= 80 for s in segments)


def test_filtergraph_has_one_crop_per_segment_and_a_two_pass_palette():
    graph = gif_filtergraph(
        [CameraSegment(0, 1000), CameraSegment(1000, 2000, Rect(x=0, y=0, width=100, height=100), 1.0)],
        frame_w=800, frame_h=600, out_width=400, out_height=300,
    )
    assert graph.count("crop=") == 2
    assert "concat=n=2" in graph
    assert "palettegen" in graph and "paletteuse" in graph


def test_every_segment_normalises_its_sample_aspect_ratio():
    """Cropping different rects gives each segment a different SAR, and concat
    refuses inputs whose SAR differs -- ffmpeg fails at configure time with
    'Input link parameters do not match'. Caught by a real render, not a unit test."""
    graph = gif_filtergraph(
        [CameraSegment(0, 1000),
         CameraSegment(1000, 2000, Rect(x=10, y=10, width=333, height=211), 1.0)],
        frame_w=980, frame_h=700, out_width=900, out_height=642,
    )
    assert graph.count("setsar=1") == 2, "each segment must reset SAR before concat"


def test_filtergraph_refuses_an_empty_timeline():
    with pytest.raises(ValueError, match="no camera segments"):
        gif_filtergraph([], frame_w=10, frame_h=10, out_width=10, out_height=10)


# ------------------------------------------------------------------- the driver

class FakeRunner:
    """Records argv and returns canned ffprobe/ffmpeg results."""

    def __init__(self, *, width=1280, height=720, duration="4.0", returncode=0):
        self.calls = []
        self._probe = json.dumps(
            {"streams": [{"width": width, "height": height, "duration": duration}],
             "format": {"duration": duration}}
        )
        self._returncode = returncode

    def __call__(self, argv, **kwargs):
        self.calls.append(argv)
        is_probe = "ffprobe" in argv[0]
        return subprocess.CompletedProcess(
            argv, self._returncode,
            stdout=self._probe if is_probe else "",
            stderr="" if self._returncode == 0 else "boom\nsomething went wrong",
        )


def test_probe_reads_dimensions_and_duration():
    info = probe_video("x.webm", runner=FakeRunner())
    assert info == VideoInfo(width=1280, height=720, duration_ms=4000)


def test_a_failing_tool_raises_with_its_stderr():
    with pytest.raises(GifRenderError, match="something went wrong"):
        probe_video("x.webm", runner=FakeRunner(returncode=1))


def test_missing_ffmpeg_says_how_to_install_it():
    with pytest.raises(FfmpegMissingError, match="brew install ffmpeg"):
        check_ffmpeg(ffmpeg="definitely-not-a-real-binary")


def test_video_to_gif_builds_the_expected_command(tmp_path):
    runner = FakeRunner()
    out = tmp_path / "demo.gif"
    asset = video_to_gif("in.webm", out, width=640, fps=10, runner=runner)

    assert asset.uri == str(out) and asset.mime == "image/gif"
    argv = runner.calls[-1]
    assert argv[0] == "ffmpeg" and "-filter_complex" in argv
    graph = argv[argv.index("-filter_complex") + 1]
    assert "fps=10" in graph
    assert "scale=640:360" in graph  # height follows the source aspect


def test_dither_reaches_the_filtergraph(tmp_path):
    """The size lever for UI captures: dithering sprays noise over flat fills."""
    runner = FakeRunner()
    video_to_gif("in.webm", tmp_path / "o.gif", dither="none", max_colors=64, runner=runner)
    graph = runner.calls[-1][runner.calls[-1].index("-filter_complex") + 1]
    assert "dither=none" in graph and "max_colors=64" in graph


def test_output_dimensions_are_even(tmp_path):
    runner = FakeRunner(width=1001, height=667)
    video_to_gif("in.webm", tmp_path / "o.gif", width=641, runner=runner)
    graph = runner.calls[-1][runner.calls[-1].index("-filter_complex") + 1]
    scale = [p for p in graph.split(";") if "scale=" in p][0].split("scale=")[1]
    w, h = (int(v) for v in scale.split(":")[:2])
    assert w % 2 == 0 and h % 2 == 0


# ------------------------------------------------------------------- the port

def _doc_with_camera(keys):
    return DemoDocument(
        id="d",
        sections=[
            Section(id="s", steps=[
                CommandStep(id="step-1", command=Command(id="noop"),
                            timing=Timing(duration_ms=4000)),
            ])
        ],
        tracks=Tracks(camera=[
            CameraKeyframe(id=f"k{i}", anchor=Anchor(step_id="step-1", local_offset_ms=at), zoom=zoom)
            for i, (at, zoom) in enumerate(keys)
        ]),
    )


def test_render_target_applies_the_documents_camera_track(tmp_path):
    runner = FakeRunner()
    doc = _doc_with_camera([(0, 1.0), (2000, 2.0)])
    target = GifRenderTarget("in.webm", tmp_path / "out.gif", width=640, runner=runner)

    asset = asyncio.run(target.export(doc))

    assert asset.mime == "image/gif"
    graph = runner.calls[-1][runner.calls[-1].index("-filter_complex") + 1]
    assert graph.count("crop=") == 2, "one crop per camera keyframe"
    assert "crop=1280:720:0:0" in graph, "the first keyframe is full frame"
    assert "crop=640:360:320:180" in graph, "the second is a centred 2x zoom"


def test_a_document_without_a_camera_renders_the_whole_video(tmp_path):
    runner = FakeRunner()
    doc = _doc_with_camera([])
    asyncio.run(GifRenderTarget("in.webm", tmp_path / "out.gif", runner=runner).export(doc))
    graph = runner.calls[-1][runner.calls[-1].index("-filter_complex") + 1]
    assert graph.count("crop=") == 1 and "concat=n=1" in graph
