"""CdpScreencastRecorder with a fake page/CDP session, and its pure helpers."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path

import pytest

from walkthru.adapters.playwright import CdpScreencastRecorder, screencast_launch_args
from walkthru.adapters.playwright.recorder import RecorderError, RecorderStateError
from walkthru.adapters.playwright.screencast import cfr_schedule, encode_argv


class FakeCdp:
    def __init__(self):
        self.sent: list[tuple[str, dict]] = []
        self.handlers = {}

    def on(self, name, handler):
        self.handlers[name] = handler

    async def send(self, method, params=None):
        self.sent.append((method, params or {}))
        return {}

    def frame(self, ts, data: bytes = b"jpeg", session: int = 1):
        metadata = {} if ts is None else {"timestamp": ts}
        self.handlers["Page.screencastFrame"](
            {"data": base64.b64encode(data).decode(), "sessionId": session,
             "metadata": metadata}
        )


class FakeContext:
    def __init__(self, cdp):
        self.cdp = cdp

    async def new_cdp_session(self, page):
        return self.cdp


class FakePage:
    def __init__(self):
        self.context = FakeContext(FakeCdp())


def test_it_records_frames_acks_them_and_encodes_a_timed_list(tmp_path):
    page, runs = FakePage(), []
    ticks = iter([9.9, 12.0])  # started, stopped
    rec = CdpScreencastRecorder(
        page, save_as=tmp_path / "tour.mp4", max_size=(1080, 1920), fps=10,
        encoder=lambda argv, frames: runs.append((argv, list(frames))), check_ffmpeg=False,
        clock=lambda: next(ticks),
    )

    async def go():
        await rec.start()
        page.context.cdp.frame(10.0, b"one")
        page.context.cdp.frame(10.5, b"two", session=2)
        await asyncio.sleep(0)
        return await rec.stop()

    asset = asyncio.run(go())
    cdp = page.context.cdp
    assert cdp.sent[0] == (
        "Page.startScreencast",
        {"format": "jpeg", "quality": 92, "everyNthFrame": 1, "maxWidth": 1080, "maxHeight": 1920},
    )
    acks = [p["sessionId"] for m, p in cdp.sent if m == "Page.screencastFrameAck"]
    assert acks == [1, 2]
    assert asset.uri == str(tmp_path / "tour.mp4") and asset.mime == "video/mp4"
    # the frames are gone once encoded (keep_frames=False), their bytes went to ffmpeg
    assert not any(p.exists() for _, p in rec.frames)
    argv, frames = runs[0]
    assert argv[-1] == str(tmp_path / "tour.mp4")
    # 2.1 s at 10 fps: the first frame held back to the start, then each until the next
    assert frames == [b"one"] * 6 + [b"two"] * 15
    # the clock: video time 0 is when recording started
    assert rec.origin == 9.9 and rec.video_time(13.4) == 3.5 and rec.video_time(9) == 0


def test_stop_before_start_and_twice_are_refused(tmp_path):
    rec = CdpScreencastRecorder(FakePage(), save_as=tmp_path / "x.mp4", encoder=lambda a, f: None,
                                check_ffmpeg=False)
    with pytest.raises(RecorderStateError):
        asyncio.run(rec.stop())


def test_no_frames_is_an_error_not_an_empty_video(tmp_path):
    rec = CdpScreencastRecorder(FakePage(), save_as=tmp_path / "x.mp4", encoder=lambda a, f: None,
                                check_ffmpeg=False)
    with pytest.raises(RecorderStateError, match="has not started"):
        rec.origin

    async def go():
        await rec.start()
        await rec.stop()

    with pytest.raises(RecorderError, match="no screencast frames"):
        asyncio.run(go())


def test_pure_helpers():
    assert screencast_launch_args(3) == ["--force-device-scale-factor=3"]
    argv = encode_argv("o.mp4", crf=20)
    assert argv[argv.index("-crf") + 1] == "20"


def test_the_schedule_is_exactly_as_long_as_the_recording_whatever_the_frame_rate():
    """60 frames a second in, 30 out, over 250 s: 7500 frames, not a second more (the
    concat-demuxer path this replaced came out 10 s long on a real tour)."""
    times = [1000 + i / 60 for i in range(60 * 250)]
    sched = cfr_schedule(times, start=1000.0, end=1250.0, fps=30)
    assert len(sched) == 7500 and sched[:3] == [0, 2, 4] and sched[-1] == 14998


@pytest.mark.skipif(__import__("shutil").which("ffmpeg") is None, reason="no ffmpeg")
def test_the_encoded_video_has_the_recordings_duration(tmp_path):
    import io
    import subprocess

    from PIL import Image

    from walkthru.adapters.playwright.screencast import _pipe_frames

    def jpeg(color):
        buf = io.BytesIO()
        Image.new("RGB", (64, 36), color).save(buf, "JPEG")
        return buf.getvalue()

    frames = [jpeg("red"), jpeg("blue")] * 45  # 90 frames at 30 fps
    out = tmp_path / "o.mp4"
    _pipe_frames(encode_argv(out, fps=30), frames)
    dur = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(out)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert abs(float(dur) - 3.0) < 0.05


def test_a_frame_without_a_timestamp_takes_its_arrival_time_and_is_still_acked(tmp_path):
    page = FakePage()
    ticks = iter([5.0, 5.4, 6.0])  # started, the frame arrived, stopped
    rec = CdpScreencastRecorder(
        page, save_as=tmp_path / "t.mp4", encoder=lambda a, f: list(f),
        clock=lambda: next(ticks), check_ffmpeg=False, keep_frames=True,
    )

    async def go():
        await rec.start()
        page.context.cdp.frame(None, b"x")
        await asyncio.sleep(0)
        await rec.stop()

    asyncio.run(go())
    assert rec.frames[0][0] == 5.4 and rec.frames[0][1].read_bytes() == b"x"
    assert any(m == "Page.screencastFrameAck" for m, _ in page.context.cdp.sent)


def test_it_only_ever_deletes_its_own_frames(tmp_path):
    shared = tmp_path / "posters"
    shared.mkdir()
    (shared / "poster.jpg").write_bytes(b"keep me")
    (shared / "000001.jpg").write_bytes(b"an old frame")
    rec = CdpScreencastRecorder(
        FakePage(), save_as=tmp_path / "t.mp4", frames_dir=shared,
        encoder=lambda a, f: None, check_ffmpeg=False,
    )
    asyncio.run(rec.start())
    assert sorted(p.name for p in shared.iterdir()) == ["poster.jpg"]


def test_no_ffmpeg_fails_at_start_not_after_the_take(tmp_path, monkeypatch):
    import walkthru.adapters.gif.render_target as rt
    from walkthru.adapters.gif import FfmpegMissingError

    monkeypatch.setattr(rt.shutil, "which", lambda name: None)
    rec = CdpScreencastRecorder(FakePage(), save_as=tmp_path / "t.mp4")
    with pytest.raises(FfmpegMissingError):
        asyncio.run(rec.start())
