"""cosmosgl executor tests: Command -> page.evaluate translation, factories, and error surfacing.

Driven with a fake page that records every ``evaluate`` call, so the whole executor is exercised
with no browser. The error-check probe is distinguished from a dispatch call by its argument: a
dispatch call passes an ``{"n", "a"}`` arg; the ``__cmderr`` probe passes none.
"""

from __future__ import annotations

import asyncio

import pytest

from walkthru.core.engine import play
from walkthru.core.schema import Command, CommandStep, DemoDocument, Section, Timing
from walkthru.ecosystem.cosmosgl import (
    CosmosglError,
    CosmosglExecutor,
    fx_command,
    graph_command,
    settle_end,
    settle_start,
)


class FakePage:
    """Records ``evaluate`` calls; returns queued errors for the ``__cmderr`` probe (arg is None)."""

    def __init__(self, cmderr_seq=()):
        self.calls: list[tuple[str, object]] = []
        self._cmderr = list(cmderr_seq)

    async def evaluate(self, expression, arg=None):
        self.calls.append((expression, arg))
        if arg is None:  # the __cmderr probe
            return self._cmderr.pop(0) if self._cmderr else None
        return {"ok": True}

    def dispatched(self):
        """Just the (expression, arg) of the dispatch calls (drop the __cmderr probes)."""
        return [(e, a) for e, a in self.calls if a is not None]


# --- factories ---------------------------------------------------------------------------


def test_factories_build_namespaced_commands_with_positional_args():
    assert graph_command("fitView", 800, 0.1, False) == Command(
        id="graph.fitView", params={"args": [800, 0.1, False]}
    )
    assert fx_command("isolate", 3) == Command(id="fx.isolate", params={"args": [3]})
    assert settle_start() == Command(id="sim.startSettle", params={"args": []})
    assert settle_end() == Command(id="sim.endSettle", params={"args": []})


# --- translation -------------------------------------------------------------------------


def test_graph_command_dispatches_to___cmd():
    page = FakePage()
    asyncio.run(CosmosglExecutor(page).play(graph_command("fitView", 800, 0.1, False)))
    (expr, arg), = page.dispatched()
    assert "window.__cmd" in expr
    assert arg == {"n": "fitView", "a": [800, 0.1, False]}


def test_fx_and_sim_commands_dispatch_to___helper():
    page = FakePage()
    asyncio.run(CosmosglExecutor(page).play(fx_command("isolate", 7)))
    asyncio.run(CosmosglExecutor(page).play(settle_start()))
    fx_call, sim_call = page.dispatched()
    assert "window['__' + p.n]" in fx_call[0]
    assert fx_call[1] == {"n": "isolate", "a": [7]}
    assert sim_call[1] == {"n": "startSettle", "a": []}


def test_unknown_namespace_raises_value_error():
    page = FakePage()
    with pytest.raises(ValueError):
        asyncio.run(CosmosglExecutor(page).play(Command(id="bogus.thing", params={"args": []})))
    with pytest.raises(ValueError):
        asyncio.run(CosmosglExecutor(page).play(Command(id="nodot", params={"args": []})))


def test_page_error_is_surfaced_as_cosmosgl_error():
    page = FakePage(cmderr_seq=["TypeError: boom"])
    with pytest.raises(CosmosglError, match="graph.fitView: TypeError: boom"):
        asyncio.run(CosmosglExecutor(page).play(graph_command("fitView", 800)))


def test_check_errors_off_skips_the_probe():
    page = FakePage(cmderr_seq=["should-not-be-read"])
    asyncio.run(CosmosglExecutor(page, check_errors=False).play(graph_command("fitView", 800)))
    # Only the dispatch call, no __cmderr probe.
    assert all(arg is not None for _, arg in page.calls)


# --- composes with the engine ------------------------------------------------------------


def test_executor_runs_a_document_through_play():
    page = FakePage()
    doc = DemoDocument(
        id="cosmosgl-demo",
        sections=[
            Section(
                id="s1",
                steps=[
                    CommandStep(id="step-1", command=settle_start(), timing=Timing(duration_ms=10)),
                    CommandStep(
                        id="step-2",
                        command=graph_command("fitView", 800, 0.1, False),
                        timing=Timing(duration_ms=10),
                    ),
                    CommandStep(id="step-3", command=fx_command("isolate", 2), timing=Timing(duration_ms=10)),
                ],
            )
        ],
    )
    outcome = asyncio.run(play(doc, CosmosglExecutor(page)))
    assert outcome.ok is True and outcome.steps_run == 3
    args = [arg for _, arg in page.dispatched()]
    assert args == [
        {"n": "startSettle", "a": []},
        {"n": "fitView", "a": [800, 0.1, False]},
        {"n": "isolate", "a": [2]},
    ]
