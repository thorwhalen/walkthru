"""Tests for the Playwright ``ReadinessWaiter``: condition dispatch, budgets, and failures.

Like the other Playwright adapters, the waiter is duck-typed over an injected page, so these tests
use in-memory fakes and need **no** ``playwright`` install and no browser — mirroring
``test_playwright_adapter.py``. Async ports are driven with ``asyncio.run`` (the suite avoids
pytest-asyncio).

The fake page raises a *builtin* ``TimeoutError`` when a gate does not hold, which is exactly the
shape the adapter recognizes structurally (it may not import Playwright's ``TimeoutError`` without
breaching the firewall).
"""

from __future__ import annotations

import asyncio

import pytest

from walkthru.adapters.playwright import (
    DEFAULT_READINESS_TIMEOUT_MS,
    PlaywrightReadinessWaiter,
    ReadinessTimeoutError,
)
from walkthru.core.schema import ElementReady, Locator, NetworkIdle, Rect, Target
from walkthru.ports import ReadinessWaiter


# --------------------------------------------------------------------------------------
# Fakes
# --------------------------------------------------------------------------------------


class _FakeLocator:
    """A fake Playwright locator carrying the candidate values behind it.

    ``or_`` concatenates candidate lists the way Playwright's ``Locator.or_`` unions match sets, so
    a test can assert that the whole prioritized ``Target`` became **one** wait on **one** budget.
    """

    def __init__(self, page: "_FakePage", values):
        self._page = page
        self.values = list(values)

    def or_(self, other: "_FakeLocator") -> "_FakeLocator":
        return _FakeLocator(self._page, [*self.values, *other.values])

    @property
    def first(self) -> "_FakeFirstLocator":
        return _FakeFirstLocator(self._page, self.values)


class _FakeFirstLocator(_FakeLocator):
    """What ``locator.first`` returns — the only object the adapter is allowed to wait on."""

    async def wait_for(self, *, state: str, timeout: int) -> None:
        self._page.element_waits.append((tuple(self.values), state, timeout))
        if not (self._page.visible & set(self.values)):
            raise TimeoutError(f"no candidate of {self.values} became {state}")


class _FakePage:
    """A fake Playwright page recording every readiness call.

    ``visible`` is the set of locator *values* that satisfy an element gate; ``reaches_idle`` says
    whether the network gate holds. Locator-builder dispatch is recorded in ``calls`` as
    ``(method, value, kwargs)`` — the same shape ``test_playwright_adapter.py`` asserts on.
    """

    def __init__(self, *, visible=(), reaches_idle: bool = True):
        self.visible = set(visible)
        self.reaches_idle = reaches_idle
        self.calls: list[tuple] = []
        self.element_waits: list[tuple] = []
        self.load_state_waits: list[tuple] = []

    def _make(self, value: str) -> _FakeLocator:
        return _FakeLocator(self, [value])

    def get_by_role(self, value, name=None):
        self.calls.append(("role", value, {"name": name}))
        return self._make(value)

    def get_by_test_id(self, value):
        self.calls.append(("testid", value, {}))
        return self._make(value)

    def get_by_text(self, value):
        self.calls.append(("text", value, {}))
        return self._make(value)

    def get_by_label(self, value):
        self.calls.append(("label", value, {}))
        return self._make(value)

    def locator(self, value):
        self.calls.append(("locator", value, {}))
        return self._make(value)

    async def wait_for_load_state(self, state: str, *, timeout: int) -> None:
        self.load_state_waits.append((state, timeout))
        if not self.reaches_idle:
            raise TimeoutError(f"load state {state!r} never reached")


def _target(primary: Locator, *fallbacks: Locator) -> Target:
    return Target(primary=primary, fallbacks=list(fallbacks))


# --------------------------------------------------------------------------------------
# ElementReady
# --------------------------------------------------------------------------------------


def test_element_ready_waits_for_the_target_to_become_visible():
    page = _FakePage(visible={"Save"})
    waiter = PlaywrightReadinessWaiter(page)
    condition = ElementReady(
        target=_target(Locator(strategy="role", value="Save", name="button")),
        timeout_ms=1500,
    )

    asyncio.run(waiter.wait(condition))

    assert page.calls == [("role", "Save", {"name": "button"})]
    assert page.element_waits == [(("Save",), "visible", 1500)]


def test_element_ready_joins_the_whole_target_into_one_timeout_budget():
    page = _FakePage(visible={"#save-btn"})
    waiter = PlaywrightReadinessWaiter(page)
    condition = ElementReady(
        target=_target(
            Locator(strategy="testid", value="save"),
            Locator(strategy="css", value="#save-btn"),
        )
    )

    asyncio.run(waiter.wait(condition))

    # Every candidate was built, primary before the fallback...
    assert [(m, v) for m, v, _ in page.calls] == [
        ("testid", "save"),
        ("locator", "#save-btn"),
    ]
    # ...and joined with ``or_`` into a single wait, so the timeout is paid once, not per candidate.
    assert page.element_waits == [
        (("save", "#save-btn"), "visible", DEFAULT_READINESS_TIMEOUT_MS)
    ]


def test_record_time_bbox_plays_no_part_in_a_readiness_gate():
    # Geometry captured at record time says nothing about whether the live element is there yet.
    page = _FakePage(visible=())
    waiter = PlaywrightReadinessWaiter(page)
    condition = ElementReady(
        target=Target(
            primary=Locator(strategy="testid", value="canvas"),
            bbox=Rect(x=0, y=0, width=10, height=10),
        ),
        timeout_ms=250,
    )

    with pytest.raises(ReadinessTimeoutError):
        asyncio.run(waiter.wait(condition))


# --------------------------------------------------------------------------------------
# NetworkIdle
# --------------------------------------------------------------------------------------


def test_network_idle_waits_on_the_page_load_state():
    page = _FakePage()
    waiter = PlaywrightReadinessWaiter(page)

    asyncio.run(waiter.wait(NetworkIdle(timeout_ms=2000)))

    assert page.load_state_waits == [("networkidle", 2000)]
    assert page.element_waits == []
    assert page.calls == []  # a network gate builds no locator


# --------------------------------------------------------------------------------------
# Timeout budget
# --------------------------------------------------------------------------------------


def test_unset_timeout_falls_back_to_the_runners_default():
    # The SSOT leaves the number to the runner; ``default_timeout_ms`` is where the runner says it.
    page = _FakePage()
    waiter = PlaywrightReadinessWaiter(page, default_timeout_ms=750)

    asyncio.run(waiter.wait(NetworkIdle()))

    assert page.load_state_waits == [("networkidle", 750)]


def test_the_default_budget_is_playwrights_own():
    assert DEFAULT_READINESS_TIMEOUT_MS == 30_000


# --------------------------------------------------------------------------------------
# Failure mapping
# --------------------------------------------------------------------------------------


def test_an_unmet_gate_raises_a_readiness_timeout_carrying_its_condition():
    page = _FakePage(visible=())  # nothing ever becomes visible
    waiter = PlaywrightReadinessWaiter(page)
    condition = ElementReady(
        target=_target(Locator(strategy="testid", value="never")), timeout_ms=250
    )

    with pytest.raises(ReadinessTimeoutError) as exc:
        asyncio.run(waiter.wait(condition))

    assert exc.value.condition is condition
    assert exc.value.timeout_ms == 250
    assert "250" in str(exc.value)
    # A subclass of the builtin, so callers may catch either.
    assert isinstance(exc.value, TimeoutError)


def test_an_unmet_network_gate_maps_the_same_way():
    page = _FakePage(reaches_idle=False)
    waiter = PlaywrightReadinessWaiter(page)

    with pytest.raises(ReadinessTimeoutError) as exc:
        asyncio.run(waiter.wait(NetworkIdle(timeout_ms=400)))

    assert exc.value.condition.kind == "networkIdle"
    assert exc.value.timeout_ms == 400


def test_a_non_timeout_failure_surfaces_as_itself():
    class _BrokenPage(_FakePage):
        async def wait_for_load_state(self, state, *, timeout):
            raise RuntimeError("browser crashed")

    waiter = PlaywrightReadinessWaiter(_BrokenPage())

    # A real fault must not be relabelled as "the condition took too long".
    with pytest.raises(RuntimeError, match="browser crashed"):
        asyncio.run(waiter.wait(NetworkIdle()))


def test_waiter_satisfies_the_port_protocol():
    assert isinstance(PlaywrightReadinessWaiter(_FakePage()), ReadinessWaiter)
