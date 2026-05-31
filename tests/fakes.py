"""In-memory fake adapters for every port — the core is tested with these, no vendor deps.

Each fake is the minimum that satisfies its :mod:`walkthru.ports` Protocol and records what it was
asked to do, so tests can assert on behavior. They double as executable documentation of the port
shapes.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

from walkthru.core.events import CommandInvocation
from walkthru.core.schema import AssetRef, Command, Cue, Rect, Target, WordTiming


class RecordingExecutor:
    """An executor (and :class:`~walkthru.ports.CommandPlayer`) that records every command.

    Usable directly as the engine's ``executor`` (it is callable) or as a ``CommandPlayer`` (it has
    ``play``). Returns a per-command canned result, defaulting to ``{"ok": True}``.
    """

    def __init__(self, results: dict[str, Any] | None = None):
        self.played: list[Command] = []
        self._results = results or {}

    async def play(self, command: Command) -> Any:
        self.played.append(command)
        return self._results.get(command.id, {"ok": True})

    async def __call__(self, command: Command) -> Any:
        return await self.play(command)


class CollectingObserver:
    """An observer that appends every event it receives (sync observer)."""

    def __init__(self) -> None:
        self.events: list[Any] = []

    def __call__(self, event: Any) -> None:
        self.events.append(event)


class FakeRecorder:
    """A :class:`~walkthru.ports.Recorder` that tracks start/stop and returns a fake asset."""

    def __init__(self) -> None:
        self.started = False
        self.stopped = False

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> AssetRef:
        self.stopped = True
        return AssetRef(uri="memory://recording.webm", mime="video/webm")


class FakeActionRecorder:
    """A :class:`~walkthru.ports.ActionRecorder` replaying a fixed list of invocations."""

    def __init__(self, invocations: list[CommandInvocation]):
        self._invocations = invocations

    async def record(self) -> AsyncIterator[CommandInvocation]:
        for invocation in self._invocations:
            yield invocation


class FakeElementLocator:
    """A :class:`~walkthru.ports.ElementLocator` returning a constant rect."""

    def __init__(self, rect: Rect | None = None):
        self._rect = rect or Rect(x=0, y=0, width=100, height=40)

    async def bounds(self, target: Target) -> Rect:
        return self._rect


class FakeCueRenderer:
    """A :class:`~walkthru.ports.CueRenderer` recording every cue it was asked to draw."""

    def __init__(self) -> None:
        self.shown: list[tuple[Cue, Rect | None]] = []

    async def show(self, cue: Cue, rect: Rect | None = None) -> None:
        self.shown.append((cue, rect))


class FakeTranscriber:
    """A :class:`~walkthru.ports.Transcriber` returning fixed word timings."""

    async def transcribe(self, audio: AssetRef) -> list[WordTiming]:
        return [WordTiming(word="hello", t_ms=0), WordTiming(word="world", t_ms=300)]


class FakeSynthesizer:
    """A :class:`~walkthru.ports.Synthesizer` returning a fake audio asset for any text."""

    async def say(self, text: str) -> AssetRef:
        return AssetRef(uri=f"memory://tts/{len(text)}.wav", mime="audio/wav")


class FakeRenderTarget:
    """A :class:`~walkthru.ports.RenderTarget` that 'exports' to a fake video asset."""

    def __init__(self) -> None:
        self.exported: list[Any] = []

    async def export(self, artifact: Any) -> AssetRef:
        self.exported.append(artifact)
        return AssetRef(uri="memory://render.mp4", mime="video/mp4")
