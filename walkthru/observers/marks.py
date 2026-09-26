"""When each step *actually* started — the bridge between a recording and its timeline.

:class:`~walkthru.observers.pacing.WallClockPacer` makes each step start at its authored moment,
but a command can still overrun its slot, and a recording started a little before the first step.
A film cut from the recording therefore needs each step's *observed* start, in the recording's own
clock, not its planned one. :class:`StepMarks` is the observer that writes those down, and
:func:`in_points` maps them into a recording that started at ``origin``.

Put it **after** the pacer in the observer list: the engine awaits observers in order, so the mark
is taken once the pacer has released the step, which is when its command is about to run.

Pure (depends only on :mod:`walkthru.core`); the clock is injected.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Mapping
from typing import Optional

from walkthru.core.events import DemoEnd, Event, StepEnter
from walkthru.core.timeline import Timeline

__all__ = ["StepMarks", "in_points", "overruns"]


class StepMarks:
    """An observer recording the wall-clock start of every step, and the end of the demo.

    >>> ticks = iter([10.0, 12.5, 20.0])
    >>> marks = StepMarks(clock=lambda: next(ticks))
    >>> from types import SimpleNamespace as NS
    >>> marks(StepEnter(step=NS(id="a"))); marks(StepEnter(step=NS(id="b")))
    >>> marks(DemoEnd(outcome=None))
    >>> marks.starts, marks.end
    ({'a': 10.0, 'b': 12.5}, 20.0)
    """

    def __init__(self, *, clock: Callable[[], float] = time.time):
        self._clock = clock
        self.starts: dict[str, float] = {}
        self.end: Optional[float] = None

    def __call__(self, event: Event) -> None:
        if isinstance(event, StepEnter):
            self.starts[event.step.id] = self._clock()
        elif isinstance(event, DemoEnd):
            self.end = self._clock()


def in_points(starts: Mapping[str, float], *, origin: float) -> dict[str, float]:
    """Each step's start, in seconds into a recording whose time 0 is wall-clock ``origin``.

    >>> in_points({"a": 100.25, "b": 103.0}, origin=100.0)
    {'a': 0.25, 'b': 3.0}
    >>> in_points({"early": 99.0}, origin=100.0)  # before the first frame: its first frame
    {'early': 0.0}
    """
    return {step: round(max(0.0, t - origin), 3) for step, t in starts.items()}


def overruns(
    timeline: Timeline,
    starts: Mapping[str, float],
    *,
    end: Optional[float] = None,
    tolerance_ms: int = 150,
) -> dict[str, int]:
    """Steps that ran longer than their slot, and by how many milliseconds.

    A cut that plays each step for its planned length loses an overrun's tail: whatever the
    command was still doing on screen. This names them, so the slot can be lengthened (or the
    command made quicker) before the film is cut.
    """
    ordered = [s for s in timeline.steps if s.step_id in starts]
    found: dict[str, int] = {}
    for i, step in enumerate(ordered):
        nxt = ordered[i + 1].step_id if i + 1 < len(ordered) else None
        stop = starts[nxt] if nxt is not None else end
        if stop is None:
            continue
        planned_ms = step.end_ms - step.start_ms + step.hold_after_ms
        over = round((stop - starts[step.step_id]) * 1000) - planned_ms
        if over > tolerance_ms:
            found[step.step_id] = over
    return found
