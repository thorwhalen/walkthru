"""The pure engine: walk a Demo Document, emit the lifecycle event stream.

One small core, one lifecycle protocol, two modes with the *driver inverted* (Report 02 §B.2):

* :func:`play` — **generative**: the executor drives. Walk the document, call ``executor`` for
  each command, and emit the lifecycle :mod:`events <walkthru.core.events>`. Observers record,
  draw, narrate.
* :func:`record` — **capture**: the human drives. Consume a stream of already-executed commands
  and assemble the *same* :class:`~walkthru.core.schema.DemoDocument`, emitting the *same*
  lifecycle so every observer behaves identically.

The engine performs exactly one injected effect — calling ``executor`` — and never records,
renders, or speaks. All other effects are injected observers/ports. ``executor`` and observers may
be sync or async; the engine awaits whatever is awaitable.
"""

from __future__ import annotations

import inspect
from collections.abc import AsyncIterator, Awaitable, Callable, Iterable
from typing import Any, Union

from walkthru.core.events import (
    AfterCommand,
    BeatEvent,
    BeforeCommand,
    CommandError,
    CommandInvocation,
    CueBegin,
    CueEnd,
    DemoEnd,
    DemoStart,
    Event,
    Narration,
    Observer,
    Outcome,
    SectionEnter,
    SectionExit,
    StepEnter,
    StepExit,
)
from walkthru.core.schema import (
    Command,
    CommandStep,
    Cue,
    DemoDocument,
    NarrationSegment,
    Section,
    Step,
    Timing,
)

#: The executor is any callable taking a :class:`~walkthru.core.schema.Command`; sync or async.
Executor = Callable[[Command], Union[Awaitable[Any], Any]]


async def _maybe_await(value: Any) -> Any:
    """Await ``value`` if it is awaitable, else return it as-is."""
    if inspect.isawaitable(value):
        return await value
    return value


def _cues_for(document: DemoDocument, step_id: str) -> Iterable[Cue]:
    """The cues anchored to ``step_id`` (anchor is the SSOT for cue-to-step association)."""
    for cue in document.tracks.cues:
        if cue.anchor.step_id == step_id:
            yield cue


def _narration_for(document: DemoDocument, step_id: str) -> Iterable[NarrationSegment]:
    """The narration segments anchored to ``step_id``."""
    for segment in document.tracks.narration:
        if segment.anchor.step_id == step_id:
            yield segment


async def iter_events(
    document: DemoDocument, executor: Executor
) -> AsyncIterator[Event]:
    """Walk ``document`` and yield the lifecycle event stream (generative mode).

    This is the canonical realization of the lifecycle protocol. The only injected effect is
    ``executor``, awaited between :class:`~walkthru.core.events.BeforeCommand` and
    :class:`~walkthru.core.events.AfterCommand`. A command that raises yields a
    :class:`~walkthru.core.events.CommandError` and the walk continues (the renderer/observer
    decides what a failed step means).
    """
    yield DemoStart(document)
    errors: list[CommandError] = []
    steps_run = 0

    for section in document.sections:
        yield SectionEnter(section)
        for step in section.steps:
            yield StepEnter(step)

            for segment in _narration_for(document, step.id):
                yield Narration(segment)

            if isinstance(step, CommandStep):
                yield BeforeCommand(step.command, step)
                try:
                    result = await _maybe_await(executor(step.command))
                except Exception as error:  # noqa: BLE001 — surfaced as a CommandError event
                    err = CommandError(step.command, error, step)
                    errors.append(err)
                    yield err
                else:
                    yield AfterCommand(step.command, result, step)
                steps_run += 1
            else:
                yield BeatEvent(step)

            for cue in _cues_for(document, step.id):
                yield CueBegin(cue)
                yield CueEnd(cue)

            yield StepExit(step)
        yield SectionExit(section)

    yield DemoEnd(Outcome(ok=not errors, steps_run=steps_run, errors=tuple(errors)))


async def _emit(event: Event, observers: Iterable[Observer]) -> None:
    """Fan one event out to every observer, awaiting async observers."""
    for observer in observers:
        await _maybe_await(observer(event))


async def play(
    document: DemoDocument,
    executor: Executor,
    *,
    observers: Iterable[Observer] = (),
) -> Outcome:
    """Play ``document`` generatively, driving ``executor`` and notifying ``observers``.

    Returns the run :class:`~walkthru.core.events.Outcome`. This is a thin driver over
    :func:`iter_events`: it forwards each event to every observer and captures the final outcome.
    """
    observers = tuple(observers)
    outcome = Outcome(ok=True, steps_run=0)
    async for event in iter_events(document, executor):
        if isinstance(event, DemoEnd):
            outcome = event.outcome
        await _emit(event, observers)
    return outcome


async def _aiter(items: Union[Iterable[Any], AsyncIterator[Any]]) -> AsyncIterator[Any]:
    """Normalize a sync or async iterable to an async iterator."""
    if hasattr(items, "__aiter__"):
        async for item in items:  # type: ignore[union-attr]
            yield item
    else:
        for item in items:  # type: ignore[union-attr]
            yield item


async def record(
    invocations: Union[Iterable[CommandInvocation], AsyncIterator[CommandInvocation]],
    *,
    observers: Iterable[Observer] = (),
    document_id: str = "capture",
    section_id: str = "captured",
    section_title: str | None = None,
    default_duration_ms: int = 1000,
) -> DemoDocument:
    """Capture mode: assemble a Demo Document from a stream of executed commands.

    Each :class:`~walkthru.core.events.CommandInvocation` becomes a
    :class:`~walkthru.core.schema.CommandStep`, and the same lifecycle events are emitted so
    observers (a logger, a video recorder, a transcriber) behave exactly as in generative mode.
    The returned document plays back through :func:`play` to reproduce the captured commands — the
    two modes are inverses over one data model.
    """
    observers = tuple(observers)
    steps: list[Step] = []

    async for invocation in _aiter(invocations):
        step = CommandStep(
            id=f"step-{len(steps) + 1}",
            command=invocation.command,
            timing=Timing(duration_ms=invocation.duration_ms or default_duration_ms),
        )
        steps.append(step)
        await _emit(StepEnter(step), observers)
        await _emit(BeforeCommand(step.command, step), observers)
        await _emit(AfterCommand(step.command, invocation.result, step), observers)
        await _emit(StepExit(step), observers)

    return DemoDocument(
        id=document_id,
        sections=[Section(id=section_id, title=section_title, steps=steps)],
    )
