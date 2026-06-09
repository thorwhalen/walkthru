"""Wall-clock pacing — replay a Demo Document in *real time* for screen recording.

The engine's :func:`~walkthru.core.engine.play` walks a document as fast as the executor returns:
correct for tests and headless capture, wrong for **filming**. To screen-record the effects a
command sequence causes, each command must fire at its *authored* moment, not back-to-back. PLAN.md
§4 already frames the recorder, overlay, narrator, **pacer**, and logger as "all just observers";
this module is that pacer.

It is a pure observer (depends only on :mod:`walkthru.core`), so it composes into any
``play(document, executor, observers=[pacer, recorder, ...])`` run and adds no schema (keeping
faith with the reserve-don't-build guardrails). The mechanism rides the engine's emit ordering:
:func:`~walkthru.core.engine.play` ``await``\\ s each observer for :class:`~walkthru.core.events.StepEnter`
*before* the generator advances to the executor call, so an observer that blocks on ``StepEnter``
genuinely delays that step's command.

* On :class:`~walkthru.core.events.DemoStart` — compose the document onto absolute time
  (:func:`~walkthru.core.timeline.resolve_timeline`) and anchor a monotonic clock.
* On :class:`~walkthru.core.events.StepEnter` — sleep until the step's absolute ``start_ms``.
  Because ``resolve_timeline`` already folds every ``hold_after_ms`` into the next step's start,
  pacing each step start reproduces the whole authored timeline with no separate hold logic.
* On :class:`~walkthru.core.events.DemoEnd` — hold until the full ``total_ms`` so the last step
  keeps its on-screen time (and trailing hold) before the recorder stops.

The clock and sleep are injected (defaults :func:`time.monotonic` / :func:`asyncio.sleep`) so the
pacer is unit-testable with a fake clock and no real time, and ``speed`` scales playback (``2.0``
for a half-time preview, ``1.0`` to film).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Optional

from walkthru.core.events import DemoEnd, DemoStart, Event, StepEnter
from walkthru.core.timeline import Timeline, resolve_timeline

#: Returns a monotonically increasing time in **seconds** (e.g. :func:`time.monotonic`).
Clock = Callable[[], float]
#: Sleeps for a number of **seconds**; awaitable (e.g. :func:`asyncio.sleep`).
Sleep = Callable[[float], Awaitable[None]]


class WallClockPacer:
    """An observer that paces a :func:`~walkthru.core.engine.play` run to the authored timeline.

    Compose it into the observer list to film a storyboard in real time::

        pacer = WallClockPacer()
        await play(document, executor, observers=[pacer, recorder])

    Args:
        clock: monotonic time source in seconds (injected for testing; default
            :func:`time.monotonic`).
        sleep: awaitable sleep in seconds (injected for testing; default :func:`asyncio.sleep`).
        speed: playback-rate multiplier; ``>1`` plays faster, ``<=0`` is rejected. Default ``1.0``.
    """

    def __init__(
        self,
        *,
        clock: Clock = time.monotonic,
        sleep: Sleep = asyncio.sleep,
        speed: float = 1.0,
    ):
        if speed <= 0:
            raise ValueError(f"speed must be positive, got {speed!r}")
        self._clock = clock
        self._sleep = sleep
        self._speed = speed
        self._t0: Optional[float] = None
        self._timeline: Optional[Timeline] = None

    async def __call__(self, event: Event) -> None:
        """Gate step execution and the final hold against the wall clock (no-op for other events)."""
        if isinstance(event, DemoStart):
            self._timeline = resolve_timeline(event.document)
            self._t0 = self._clock()
        elif isinstance(event, StepEnter):
            if self._timeline is not None:
                await self._wait_until_ms(self._timeline.step(event.step.id).start_ms)
        elif isinstance(event, DemoEnd):
            if self._timeline is not None:
                await self._wait_until_ms(self._timeline.total_ms)

    async def _wait_until_ms(self, target_ms: int) -> None:
        """Sleep until ``target_ms`` of authored time has elapsed since ``DemoStart`` (scaled by speed)."""
        target_s = (target_ms / 1000.0) / self._speed
        elapsed_s = self._clock() - (self._t0 or 0.0)
        remaining_s = target_s - elapsed_s
        if remaining_s > 0:
            await self._sleep(remaining_s)
