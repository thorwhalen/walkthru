"""Pacer tests: the wall-clock pacer sleeps each step to its authored absolute time.

Driven with a fake clock whose ``sleep`` is the only thing that advances time, so the pacer's
requested sleeps are exact and deterministic — no real wall time elapses.
"""

from __future__ import annotations

import asyncio

from walkthru.core.engine import play
from walkthru.observers import WallClockPacer

from tests.builders import make_minimal_demo
from tests.fakes import RecordingExecutor


class FakeClock:
    """A deterministic clock where only :meth:`sleep` advances time (recording every sleep)."""

    def __init__(self) -> None:
        self.t = 0.0
        self.slept: list[float] = []

    def now(self) -> float:
        return self.t

    async def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.t += seconds


def _run(pacer: WallClockPacer, clock: FakeClock):
    # make_minimal_demo: step-1 [0,500), step-2 starts at 500 (hold 200), total_ms 1500.
    executor = RecordingExecutor()
    outcome = asyncio.run(play(make_minimal_demo(), executor, observers=[pacer]))
    return outcome, executor, clock


def test_pacer_sleeps_to_each_step_start_and_final_total():
    clock = FakeClock()
    outcome, executor, clock = _run(
        WallClockPacer(clock=clock.now, sleep=clock.sleep), clock
    )
    # step-1 starts at 0 (no sleep, elapsed already 0); step-2 at 500ms -> sleep 0.5s;
    # DemoEnd holds to total 1500ms, with 0.5s already elapsed -> sleep 1.0s.
    assert clock.slept == [0.5, 1.0]
    # Pacing does not disturb execution order/outcome.
    assert outcome.ok is True
    assert [c.id for c in executor.played] == ["app.open", "app.click"]


def test_speed_multiplier_scales_the_waits():
    clock = FakeClock()
    _run(WallClockPacer(clock=clock.now, sleep=clock.sleep, speed=2.0), clock)
    # At 2x: step-2 at 250ms -> 0.25s; final total 750ms with 0.25s elapsed -> 0.5s.
    assert clock.slept == [0.25, 0.5]


def test_non_positive_speed_is_rejected():
    for bad in (0, -1.0):
        try:
            WallClockPacer(speed=bad)
        except ValueError:
            pass
        else:  # pragma: no cover - guard
            raise AssertionError(f"speed={bad!r} should have raised ValueError")


def test_pacer_defaults_need_no_injection():
    # Constructing with defaults (time.monotonic / asyncio.sleep) must not require arguments.
    pacer = WallClockPacer()
    assert pacer is not None
