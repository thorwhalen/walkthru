"""The injected ports — thin facades the engine and adapters speak through.

Every effect walkthru performs is behind one of these :class:`~typing.Protocol` ports. The core
and these ports import **nothing** from :mod:`walkthru.adapters` or :mod:`walkthru.ecosystem`, and
no vendor type ever crosses a port boundary — that firewall is what keeps the core runnable and
publishable with zero hard dependency on any vendor SDK or ecosystem package (brief §4, §6).

Ports are interfaces only; real implementations live in :mod:`walkthru.adapters` (e.g. Playwright,
OBS, WhisperX, Piper) and :mod:`walkthru.ecosystem` (acture, reelee), and in-memory fakes live in
the test suite. The ports are deliberately ``async`` because their real implementations do I/O
(browser automation, recording, transcription); the engine awaits whatever is awaitable.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any, Protocol, runtime_checkable

from walkthru.core.events import CommandInvocation
from walkthru.core.schema import (
    AssetRef,
    Command,
    Cue,
    DemoDocument,
    Rect,
    Target,
    WordTiming,
)


@runtime_checkable
class CommandPlayer(Protocol):
    """Runs a command. The engine's ``executor`` is typically ``CommandPlayer.play``."""

    async def play(self, command: Command) -> Any: ...


@runtime_checkable
class Recorder(Protocol):
    """Records the screen to a media asset."""

    async def start(self) -> None: ...

    async def stop(self) -> AssetRef: ...


@runtime_checkable
class ActionRecorder(Protocol):
    """Yields the human's commands as they happen — the capture-mode input stream."""

    def record(self) -> AsyncIterator[CommandInvocation]: ...


@runtime_checkable
class ElementLocator(Protocol):
    """Resolves a resilient :class:`~walkthru.core.schema.Target` to current geometry."""

    async def bounds(self, target: Target) -> Rect: ...


@runtime_checkable
class CueRenderer(Protocol):
    """Draws a cue (optionally at a resolved rect)."""

    async def show(self, cue: Cue, rect: Rect | None = None) -> None: ...


@runtime_checkable
class Transcriber(Protocol):
    """Speech-to-text with word-level timing (e.g. WhisperX)."""

    async def transcribe(self, audio: AssetRef) -> list[WordTiming]: ...


@runtime_checkable
class Synthesizer(Protocol):
    """Text-to-speech (e.g. Piper / a hosted voice)."""

    async def say(self, text: str) -> AssetRef: ...


@runtime_checkable
class RenderTarget(Protocol):
    """Exports a validated Demo Document to a rendered video (e.g. reelee)."""

    async def export(self, artifact: DemoDocument) -> AssetRef: ...


__all__ = [
    "CommandPlayer",
    "Recorder",
    "ActionRecorder",
    "ElementLocator",
    "CueRenderer",
    "Transcriber",
    "Synthesizer",
    "RenderTarget",
]
