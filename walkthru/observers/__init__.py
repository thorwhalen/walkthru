"""Reusable, dependency-free observers for :func:`~walkthru.core.engine.play`.

PLAN.md §4 frames the recorder, overlay, narrator, pacer, and logger as "all just observers". This
package is the home for the ones that are *pure* — depending only on :mod:`walkthru.core`, with no
vendor SDK — so they import and test without any optional extra. Vendor-backed observers (a
Playwright recorder, a driver.js cue renderer) live in :mod:`walkthru.adapters` /
:mod:`walkthru.ecosystem` instead, behind the ports firewall.

Currently: :class:`~walkthru.observers.pacing.WallClockPacer`, which replays a Demo Document in
real time so a screen recorder films each command at its authored moment.
"""

from walkthru.observers.pacing import Clock, Sleep, WallClockPacer

__all__ = ["WallClockPacer", "Clock", "Sleep"]
