"""The lifecycle protocol, as a typed event stream.

The brief describes the engine's lifecycle as a set of named observer hooks (``onStepEnter``,
``beforeCommand``, ...). walkthru realizes that protocol as a stream of **typed events** consumed
by observer **callables** — the functional equivalent (each event type corresponds 1:1 to a hook
name), chosen for composability and to match Thor's functional conventions. See ``DECISIONS.md``
§D9.

An :data:`Observer` is any callable taking one :data:`Event`; it may be sync or async. The engine
(:mod:`walkthru.core.engine`) emits events; observers are pure subscribers — a recorder, an
overlay renderer, a narrator, a pacer, and a logger are all just observers.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any, Union

from walkthru.core.schema import (
    Beat,
    Command,
    CommandStep,
    Cue,
    DemoDocument,
    NarrationSegment,
    Section,
    Step,
)


@dataclass(frozen=True)
class Outcome:
    """The result of a play/record run."""

    ok: bool
    steps_run: int
    errors: tuple["CommandError", ...] = field(default_factory=tuple)


# --- lifecycle events (one type per hook in the protocol) ---


@dataclass(frozen=True)
class DemoStart:
    """Emitted once, before any section."""

    document: DemoDocument


@dataclass(frozen=True)
class DemoEnd:
    """Emitted once, after the last section; carries the run :class:`Outcome`."""

    outcome: Outcome


@dataclass(frozen=True)
class SectionEnter:
    section: Section


@dataclass(frozen=True)
class SectionExit:
    section: Section


@dataclass(frozen=True)
class StepEnter:
    step: Step


@dataclass(frozen=True)
class StepExit:
    step: Step


@dataclass(frozen=True)
class BeforeCommand:
    """Emitted just before the executor runs the command."""

    command: Command
    step: CommandStep


@dataclass(frozen=True)
class AfterCommand:
    """Emitted after the executor returns successfully."""

    command: Command
    result: Any
    step: CommandStep


@dataclass(frozen=True)
class CommandError:
    """Emitted when the executor raises; the run continues unless an observer stops it."""

    command: Command
    error: BaseException
    step: CommandStep


@dataclass(frozen=True)
class CueBegin:
    cue: Cue


@dataclass(frozen=True)
class CueEnd:
    cue: Cue


@dataclass(frozen=True)
class Narration:
    segment: NarrationSegment


@dataclass(frozen=True)
class BeatEvent:
    beat: Beat


Event = Union[
    DemoStart,
    DemoEnd,
    SectionEnter,
    SectionExit,
    StepEnter,
    StepExit,
    BeforeCommand,
    AfterCommand,
    CommandError,
    CueBegin,
    CueEnd,
    Narration,
    BeatEvent,
]

#: An observer is any callable that consumes an event; it may return ``None`` or an awaitable.
Observer = Callable[[Event], Union[Awaitable[None], None]]


@dataclass(frozen=True)
class CommandInvocation:
    """A command that has already executed — the unit of the capture-mode input stream.

    In capture mode the human drives the app, each dispatch is observed *after the fact*, and the
    engine records it. ``result``/``durationMs`` are what the live dispatch returned.
    """

    command: Command
    result: Any = None
    duration_ms: int | None = None
