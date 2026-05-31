"""Engine tests: the generative walk, the capture mode, and that the two are inverses."""

from __future__ import annotations

import asyncio

from walkthru.core.engine import play, record
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

from tests.builders import make_minimal_demo, make_rich_demo
from tests.fakes import CollectingObserver, RecordingExecutor


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
