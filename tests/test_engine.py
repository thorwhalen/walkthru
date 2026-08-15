"""Engine tests: the generative walk, readiness gates, capture mode, and that play/record invert."""

from __future__ import annotations

import asyncio

import pytest

from walkthru.core.engine import iter_events, play, record
from walkthru.core.events import (
    AfterCommand,
    BeforeCommand,
    CommandError,
    CommandInvocation,
    CueBegin,
    CueEnd,
    DemoEnd,
    DemoStart,
    Narration,
    StepEnter,
    StepExit,
)
from walkthru.core.schema import Command, DemoDocument

from tests.builders import make_gated_demo, make_minimal_demo, make_rich_demo
from tests.fakes import CollectingObserver, FakeReadinessWaiter, RecordingExecutor


def test_play_runs_commands_in_order():
    doc = make_minimal_demo()
    executor = RecordingExecutor()
    outcome = asyncio.run(play(doc, executor))

    assert outcome.ok is True
    assert outcome.steps_run == 2
    assert [c.id for c in executor.played] == ["app.open", "app.click"]
    assert executor.played[1].params == {"x": 1, "y": 2}


def test_play_emits_wrapped_lifecycle():
    doc = make_minimal_demo()
    obs = CollectingObserver()
    asyncio.run(play(doc, RecordingExecutor(), observers=[obs]))

    kinds = [type(e).__name__ for e in obs.events]
    # Brackets: the stream opens with DemoStart and closes with DemoEnd.
    assert kinds[0] == "DemoStart"
    assert kinds[-1] == "DemoEnd"
    # Each command step is wrapped: StepEnter -> BeforeCommand -> AfterCommand -> StepExit.
    first = [
        type(e).__name__
        for e in obs.events
        if isinstance(e, (StepEnter, BeforeCommand, AfterCommand, StepExit))
    ][:4]
    assert first == ["StepEnter", "BeforeCommand", "AfterCommand", "StepExit"]


def test_rich_demo_emits_cue_and_narration_events():
    doc = make_rich_demo()
    obs = CollectingObserver()
    asyncio.run(play(doc, RecordingExecutor(), observers=[obs]))

    narrations = [e for e in obs.events if isinstance(e, Narration)]
    assert [n.segment.id for n in narrations] == ["n1"]

    cue_begins = [e for e in obs.events if isinstance(e, CueBegin)]
    cue_ends = [e for e in obs.events if isinstance(e, CueEnd)]
    assert {c.cue.id for c in cue_begins} == {"c1", "c2"}
    assert len(cue_begins) == len(cue_ends) == 2


def test_command_error_is_surfaced_and_walk_continues():
    doc = make_minimal_demo()

    async def flaky(command: Command):
        if command.id == "app.open":
            raise RuntimeError("boom")
        return {"ok": True}

    obs = CollectingObserver()
    outcome = asyncio.run(play(doc, flaky, observers=[obs]))

    errors = [e for e in obs.events if isinstance(e, CommandError)]
    assert len(errors) == 1
    assert isinstance(errors[0].error, RuntimeError)
    assert outcome.ok is False
    assert len(outcome.errors) == 1
    # The walk did not stop: the second step's DemoEnd still arrived.
    assert isinstance(obs.events[-1], DemoEnd)


def test_async_and_sync_observers_both_supported():
    doc = make_minimal_demo()
    seen: list[str] = []

    def sync_obs(event):
        seen.append("s")

    async def async_obs(event):
        seen.append("a")

    asyncio.run(play(doc, RecordingExecutor(), observers=[sync_obs, async_obs]))
    assert seen.count("s") == seen.count("a") > 0


def test_waiter_receives_the_declared_condition():
    doc = make_gated_demo()
    waiter = FakeReadinessWaiter()

    outcome = asyncio.run(play(doc, RecordingExecutor(), waiter=waiter.wait))

    assert outcome.ok is True
    assert [c.kind for c in waiter.awaited] == ["element"]
    assert waiter.awaited[0].timeout_ms == 5000


def test_gate_resolves_after_the_command_and_before_its_cues():
    """The whole point of the gate: a cue may not fire before the thing it points at is there."""
    doc = make_gated_demo()
    log: list[str] = []

    async def waiter(condition):
        log.append(f"wait:{condition.kind}")

    def observer(event):
        log.append(type(event).__name__)

    asyncio.run(play(doc, RecordingExecutor(), observers=[observer], waiter=waiter))

    assert log == [
        "DemoStart",
        "SectionEnter",
        "StepEnter",
        "BeforeCommand",
        "AfterCommand",
        "wait:element",
        "CueBegin",
        "CueEnd",
        "StepExit",
        "SectionExit",
        "DemoEnd",
    ]


def test_gate_is_skipped_when_the_command_never_ran():
    doc = make_gated_demo()
    waiter = FakeReadinessWaiter()

    async def broken(command):
        raise RuntimeError("boom")

    outcome = asyncio.run(play(doc, broken, waiter=waiter.wait))

    assert outcome.ok is False
    # Waiting for the effect of a command that never ran only burns the timeout.
    assert waiter.awaited == []


def test_declaring_a_gate_without_a_waiter_is_a_wiring_error():
    doc = make_gated_demo()

    with pytest.raises(ValueError) as exc:
        asyncio.run(play(doc, RecordingExecutor()))

    assert "step-1" in str(exc.value)
    assert "timing.waitFor" in str(exc.value)


def test_the_missing_waiter_error_fits_every_entry_point():
    """``iter_events`` is public too, so the message must not name a function the caller skipped."""
    doc = make_gated_demo()

    async def drain():
        async for _ in iter_events(doc, RecordingExecutor()):
            pass

    with pytest.raises(ValueError) as exc:
        asyncio.run(drain())

    assert "play()" not in str(exc.value)


def test_an_unmet_gate_aborts_the_run():
    doc = make_gated_demo()
    waiter = FakeReadinessWaiter(fail_on="element")
    obs = CollectingObserver()

    with pytest.raises(TimeoutError):
        asyncio.run(play(doc, RecordingExecutor(), observers=[obs], waiter=waiter.wait))

    # Deliberate: an unmet precondition is not collected like a command error — everything after it
    # would be filmed against an unknown screen. The consequence, documented on the port, is that
    # the run ends *without* DemoEnd, so observers holding resources are the caller's to close.
    assert not any(isinstance(e, DemoEnd) for e in obs.events)


def test_record_builds_document_from_stream():
    invocations = [
        CommandInvocation(Command(id="app.open")),
        CommandInvocation(
            Command(id="app.click", params={"x": 1}), result={"ok": True}
        ),
    ]
    doc = asyncio.run(record(invocations))

    assert isinstance(doc, DemoDocument)
    assert len(doc.sections) == 1
    steps = doc.sections[0].steps
    assert [s.command.id for s in steps] == ["app.open", "app.click"]


def test_capture_and_play_are_inverses():
    """record(stream) -> document, then play(document) reproduces the captured commands."""
    invocations = [
        CommandInvocation(Command(id="app.open")),
        CommandInvocation(Command(id="app.click", params={"x": 1})),
        CommandInvocation(Command(id="app.save")),
    ]
    doc = asyncio.run(record(invocations))

    executor = RecordingExecutor()
    asyncio.run(play(doc, executor))

    assert [c.id for c in executor.played] == ["app.open", "app.click", "app.save"]
    assert executor.played[1].params == {"x": 1}
