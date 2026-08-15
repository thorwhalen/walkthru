"""Playwright ``ReadinessWaiter`` — block until a step's ``timing.waitFor`` condition holds.

walkthru's first real :class:`~walkthru.ports.ReadinessWaiter` (issue #18). Screen-recording a
generative run is only reliable if the runner can tell when an effect has actually landed: a page
navigates, and the WebGL canvas it renders shows up seconds later. A fixed sleep guesses; a
readiness gate observes. This adapter is the observing half, mapping the schema's two declarative
conditions onto Playwright's own waiting primitives:

- :class:`~walkthru.core.schema.ElementReady` → ``locator.first.wait_for(state="visible")`` over
  the whole :class:`~walkthru.core.schema.Target`. ``primary`` and every ``fallback`` are joined
  with Playwright's ``Locator.or_`` so the whole candidate set shares **one** timeout budget,
  rather than paying the timeout once per candidate. Precisely: the gate holds when the first
  candidate *in DOM order* becomes visible — ``.first`` is re-resolved on every poll, so a
  present-but-hidden candidate earlier in the document can hold the gate open even while a later
  one is visible. ``Target.bbox`` is deliberately unused — record-time geometry says nothing about
  whether the live element exists.
- :class:`~walkthru.core.schema.NetworkIdle` → ``page.wait_for_load_state("networkidle")``.

"Appeared **and settled**" is expressed as ``waitFor`` + the step's existing ``holdAfterMs`` — the
gate observes arrival, the hold covers the animation. That is why there is no ``settled``
condition: the schema already had the second half.

Like the locator and recorder, this imports nothing from ``playwright`` at runtime — it drives an
injected, duck-typed page — so the core stays vendor-free and it is unit-testable with a fake.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from walkthru.adapters.playwright.locator import build_locator
from walkthru.core.schema import ElementReady, NetworkIdle, Target, WaitFor

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page

#: Playwright's own default action timeout; used when a condition leaves ``timeoutMs`` unset.
DEFAULT_READINESS_TIMEOUT_MS = 30_000


class ReadinessTimeoutError(TimeoutError):
    """A ``timing.waitFor`` condition did not hold within its timeout."""

    def __init__(self, condition: WaitFor, timeout_ms: int):
        self.condition = condition
        self.timeout_ms = timeout_ms
        super().__init__(
            f"readiness condition {condition.kind!r} was not met within {timeout_ms} ms"
        )


def _any_of(page: Any, target: Target) -> Any:
    """One Playwright locator matching ``primary`` **or** any ``fallback``.

    ``Locator.or_`` is what lets the whole prioritized Target share a single timeout. The list
    order does not decide the winner — the union is re-resolved on each poll and ``.first`` takes
    the earliest *DOM-order* match (see the module docstring).
    """
    locator = build_locator(page, target.primary)
    for fallback in target.fallbacks:
        locator = locator.or_(build_locator(page, fallback))
    return locator


class PlaywrightReadinessWaiter:
    """A :class:`~walkthru.ports.ReadinessWaiter` backed by Playwright's waiting primitives.

    Args:
        page: a Playwright ``Page`` (injected, duck-typed — see the module docstring).
        default_timeout_ms: the budget for a condition whose ``timeoutMs`` is ``None``. The SSOT
            deliberately leaves the number to the runner, and this is the runner.
    """

    def __init__(
        self,
        page: "Page",
        *,
        default_timeout_ms: int = DEFAULT_READINESS_TIMEOUT_MS,
    ):
        self._page = page
        self._default_timeout_ms = default_timeout_ms

    async def wait(self, condition: WaitFor) -> None:
        """Block until ``condition`` holds, or raise :class:`ReadinessTimeoutError`."""
        timeout_ms = (
            condition.timeout_ms
            if condition.timeout_ms is not None
            else self._default_timeout_ms
        )
        try:
            await self._apply(condition, timeout_ms)
        except Exception as error:
            # The firewall forbids importing ``playwright`` to name its TimeoutError, so it is
            # recognized structurally (the builtin has the same name, so a fake times out too).
            # Anything else is a real fault and must surface as itself, not as a timeout.
            if type(error).__name__ != "TimeoutError":
                raise
            raise ReadinessTimeoutError(condition, timeout_ms) from error

    async def _apply(self, condition: WaitFor, timeout_ms: int) -> None:
        """Dispatch one condition onto the matching Playwright primitive."""
        if isinstance(condition, ElementReady):
            locator = _any_of(self._page, condition.target)
            await locator.first.wait_for(state="visible", timeout=timeout_ms)
            return
        if isinstance(condition, NetworkIdle):
            await self._page.wait_for_load_state("networkidle", timeout=timeout_ms)
            return
        # Unreachable: ``kind`` is a schema ``Literal`` validated at construction.
        raise ValueError(f"unknown readiness condition: {condition!r}")
