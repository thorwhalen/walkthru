"""StepMarks / in_points / overruns: from observed step starts to cut points in a recording."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace as NS

from walkthru import Command, CommandStep, DemoDocument, Section, Timing, play
from walkthru.core.events import DemoEnd, StepEnter
from walkthru.core.timeline import resolve_timeline
from walkthru.observers import StepMarks, WallClockPacer, in_points, overruns


def _doc(*ms):
    return DemoDocument(
        id="d",
        sections=[
            Section(
                id="s",
                steps=[
                    CommandStep(id=f"s{i}", command=Command(id="x"), timing=Timing(duration_ms=m))
                    for i, m in enumerate(ms)
                ],
            )
        ],
    )


def test_marks_follow_the_pacer_when_listed_after_it():
    """With a fake clock the pacer 'sleeps' by advancing it; the marks land on the
    authored starts because the engine awaits observers in order."""
    now = [100.0]

    async def sleep(s):
        now[0] += s

    clock = lambda: now[0]  # noqa: E731
    pacer = WallClockPacer(clock=clock, sleep=sleep)
    marks = StepMarks(clock=clock)

    async def executor(command):
        now[0] += 0.2  # every command takes 200 ms
        return {"ok": True}

    asyncio.run(play(_doc(1000, 2000, 500), executor, observers=[pacer, marks]))
    assert marks.starts == {"s0": 100.0, "s1": 101.0, "s2": 103.0}
    assert marks.end == 103.5
    assert in_points(marks.starts, origin=99.5) == {"s0": 0.5, "s1": 1.5, "s2": 3.5}


def test_overruns_names_a_step_that_outlasted_its_slot():
    tl = resolve_timeline(_doc(1000, 1000, 1000))
    starts = {"s0": 0.0, "s1": 1.05, "s2": 2.9}
    assert overruns(tl, starts, end=3.9) == {"s1": 850}
    assert overruns(tl, starts, end=3.9, tolerance_ms=900) == {}


def test_marks_ignore_everything_but_step_starts_and_the_end():
    marks = StepMarks(clock=lambda: 5.0)
    marks(NS())
    assert marks.starts == {} and marks.end is None
    marks(StepEnter(step=NS(id="a")))
    marks(DemoEnd(outcome=None))
    assert marks.starts == {"a": 5.0} and marks.end == 5.0
