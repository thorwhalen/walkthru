"""Tests for the Playwright adapters: ``ElementLocator`` bounds + ``Recorder`` start/stop.

Both adapters are duck-typed over an injected Playwright object, so these tests use in-memory
fakes and need **no** ``playwright`` install and no browser — mirroring the firewall discipline the
suite enforces elsewhere. Async ports are driven with ``asyncio.run`` (the suite avoids
pytest-asyncio).
"""

from __future__ import annotations

import asyncio
import importlib
import sys

import pytest

from walkthru.adapters.playwright import (
    ElementNotFoundError,
    PlaywrightElementLocator,
    PlaywrightRecorder,
    RecorderError,
    RecorderStateError,
    new_recording_page,
)
from walkthru.core.schema import AssetRef, Locator, Rect, Target
from walkthru.ports import ElementLocator, Recorder


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class _FakeLocator:
    """A fake Playwright locator: a fixed ``count`` and a fixed ``bounding_box``."""

    def __init__(self, *, count: int, box):
        self._count = count
        self._box = box

    async def count(self) -> int:
        return self._count

    @property
    def first(self) -> "_FakeLocator":
        return self

    async def bounding_box(self):
        return self._box


class _FakePage:
    """A fake Playwright page. ``boxes`` maps a locator *value* to its bounding box.

    A value present with a dict box → matches & visible. A value mapped to ``None`` → matches but
    not visible (``bounding_box`` is ``None``). A value absent → no match (``count`` is 0). Every
    builder call is recorded in ``calls`` as ``(method, value, kwargs)``.
    """

    def __init__(self, boxes=None):
        self._boxes = boxes or {}
        self.calls: list[tuple] = []

    def _make(self, value: str) -> _FakeLocator:
        if value in self._boxes:
            return _FakeLocator(count=1, box=self._boxes[value])
        return _FakeLocator(count=0, box=None)

    def get_by_role(self, value, name=None):
        self.calls.append(("role", value, {"name": name}))
        return self._make(value)

    def get_by_test_id(self, value):
        self.calls.append(("testid", value, {}))
        return self._make(value)

    def get_by_text(self, value):
        self.calls.append(("text", value, {}))
        return self._make(value)

    def get_by_label(self, value):
        self.calls.append(("label", value, {}))
        return self._make(value)

    def locator(self, value):
        self.calls.append(("locator", value, {}))
        return self._make(value)


class _FakeVideo:
    def __init__(self, path="/tmp/walkthru-fake/video.webm"):
        self._path = path
        self.saved_to = None

    async def path(self):
        return self._path

    async def save_as(self, dest):
        self.saved_to = dest


class _FakeRecordingPage:
    def __init__(self, *, video=None):
        self.video = video
        self.closed = False

    async def close(self):
        self.closed = True


class _FakeContext:
    def __init__(self):
        self.page = _FakeRecordingPage(video=_FakeVideo())

    async def new_page(self):
        return self.page


class _FakeBrowser:
    def __init__(self):
        self.context_kwargs = None
        self.context = _FakeContext()

    async def new_context(self, **kwargs):
        self.context_kwargs = kwargs
        return self.context


def _target(primary: Locator, *fallbacks: Locator, bbox: Rect | None = None) -> Target:
    return Target(primary=primary, fallbacks=list(fallbacks), bbox=bbox)


# --------------------------------------------------------------------------------------
# ElementLocator
# --------------------------------------------------------------------------------------


def test_primary_locator_resolves_to_its_bounding_box():
    page = _FakePage({"Save": {"x": 10, "y": 20, "width": 80, "height": 30}})
    locator = PlaywrightElementLocator(page)
    target = _target(Locator(strategy="role", value="Save", name="button"))

    rect = asyncio.run(locator.bounds(target))

    assert rect == Rect(x=10, y=20, width=80, height=30)


def test_falls_back_to_next_locator_when_primary_misses():
    page = _FakePage({"#save-btn": {"x": 1, "y": 2, "width": 3, "height": 4}})
    locator = PlaywrightElementLocator(page)
    target = _target(
        Locator(strategy="testid", value="save"),  # absent -> count 0
        Locator(strategy="css", value="#save-btn"),  # present
    )

    rect = asyncio.run(locator.bounds(target))

    assert rect == Rect(x=1, y=2, width=3, height=4)
    # Both candidates were tried, primary before the fallback.
    tried = [(m, v) for m, v, _ in page.calls]
    assert tried == [("testid", "save"), ("locator", "#save-btn")]


def test_present_but_invisible_element_is_not_a_match():
    # Matches (count 1) but bounding_box is None -> treat as unresolved, fall through to bbox.
    page = _FakePage({"ghost": None})
    locator = PlaywrightElementLocator(page)
    bbox = Rect(x=5, y=5, width=5, height=5)
    target = _target(Locator(strategy="css", value="ghost"), bbox=bbox)

    rect = asyncio.run(locator.bounds(target))

    assert rect == bbox


def test_record_time_bbox_is_the_last_resort():
    page = _FakePage({})  # nothing resolves
    locator = PlaywrightElementLocator(page)
    bbox = Rect(x=7, y=8, width=9, height=10)
    target = _target(Locator(strategy="role", value="Missing", name="button"), bbox=bbox)

    rect = asyncio.run(locator.bounds(target))

    assert rect == bbox


def test_raises_when_nothing_resolves_and_no_bbox():
    page = _FakePage({})
    locator = PlaywrightElementLocator(page)
    target = _target(
        Locator(strategy="testid", value="nope"),
        Locator(strategy="text", value="also nope"),
    )

    with pytest.raises(ElementNotFoundError) as exc:
        asyncio.run(locator.bounds(target))

    # The error names the candidates it tried, for a debuggable failure.
    assert "nope" in str(exc.value)
    assert "also nope" in str(exc.value)
    assert exc.value.target is target


def test_strategy_to_playwright_getter_mapping():
    page = _FakePage()  # every call returns count 0; we only assert the dispatch
    locator = PlaywrightElementLocator(page)
    target = _target(
        Locator(strategy="role", value="tablist", name="Views"),
        Locator(strategy="testid", value="panel-3"),
        Locator(strategy="text", value="Save"),
        Locator(strategy="label", value="Email"),
        Locator(strategy="css", value=".btn"),
        Locator(strategy="xpath", value="//button"),
    )

    with pytest.raises(ElementNotFoundError):
        asyncio.run(locator.bounds(target))

    assert page.calls == [
        ("role", "tablist", {"name": "Views"}),
        ("testid", "panel-3", {}),
        ("text", "Save", {}),
        ("label", "Email", {}),
        ("locator", ".btn", {}),
        ("locator", "xpath=//button", {}),  # xpath gets the engine prefix
    ]


def test_locator_satisfies_the_port_protocol():
    assert isinstance(PlaywrightElementLocator(_FakePage()), ElementLocator)


# --------------------------------------------------------------------------------------
# Recorder
# --------------------------------------------------------------------------------------


def test_recorder_start_stop_returns_video_asset():
    page = _FakeRecordingPage(video=_FakeVideo("/tmp/walkthru-fake/rec.webm"))
    recorder = PlaywrightRecorder(page)

    asyncio.run(recorder.start())
    asset = asyncio.run(recorder.stop())

    assert asset == AssetRef(uri="/tmp/walkthru-fake/rec.webm", mime="video/webm")
    assert page.closed is True  # closing the page finalizes the screencast


def test_recorder_save_as_writes_to_stable_path(tmp_path):
    dest = tmp_path / "out" / "demo.webm"
    video = _FakeVideo()
    page = _FakeRecordingPage(video=video)
    recorder = PlaywrightRecorder(page, save_as=dest)

    asyncio.run(recorder.start())
    asset = asyncio.run(recorder.stop())

    assert video.saved_to == str(dest)
    assert asset.uri == str(dest)
    assert dest.parent.is_dir()  # parent created on demand


def test_recorder_stop_before_start_is_an_error():
    recorder = PlaywrightRecorder(_FakeRecordingPage(video=_FakeVideo()))
    with pytest.raises(RecorderStateError):
        asyncio.run(recorder.stop())


def test_recorder_double_start_is_an_error():
    recorder = PlaywrightRecorder(_FakeRecordingPage(video=_FakeVideo()))
    asyncio.run(recorder.start())
    with pytest.raises(RecorderStateError):
        asyncio.run(recorder.start())


def test_recorder_double_stop_is_an_error():
    recorder = PlaywrightRecorder(_FakeRecordingPage(video=_FakeVideo()))
    asyncio.run(recorder.start())
    asyncio.run(recorder.stop())
    with pytest.raises(RecorderStateError):
        asyncio.run(recorder.stop())


def test_recorder_without_video_raises_informative_error():
    page = _FakeRecordingPage(video=None)  # context wasn't created with record_video_dir
    recorder = PlaywrightRecorder(page)
    asyncio.run(recorder.start())
    with pytest.raises(RecorderError) as exc:
        asyncio.run(recorder.stop())
    assert "record_video_dir" in str(exc.value)


def test_recorder_satisfies_the_port_protocol():
    assert isinstance(PlaywrightRecorder(_FakeRecordingPage()), Recorder)


def test_new_recording_page_configures_context_level_recording(tmp_path):
    browser = _FakeBrowser()

    context, page = asyncio.run(
        new_recording_page(
            browser,
            record_video_dir=tmp_path,
            record_video_size={"width": 1280, "height": 720},
        )
    )

    assert browser.context_kwargs["record_video_dir"] == str(tmp_path)
    assert browser.context_kwargs["record_video_size"] == {"width": 1280, "height": 720}
    assert context is browser.context
    assert page is browser.context.page


# --------------------------------------------------------------------------------------
# Firewall: the adapter must not import the real ``playwright`` package
# --------------------------------------------------------------------------------------


def test_importing_the_adapter_pulls_in_no_playwright():
    for name in [m for m in sys.modules if m == "playwright" or m.startswith("playwright.")]:
        del sys.modules[name]
    importlib.import_module("walkthru.adapters.playwright")
    leaked = [m for m in sys.modules if m == "playwright" or m.startswith("playwright.")]
    assert not leaked, f"adapter import leaked real playwright modules: {leaked}"
