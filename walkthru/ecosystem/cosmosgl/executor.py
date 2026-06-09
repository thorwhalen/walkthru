"""The cosmos.gl ``Executor`` — drive a live ``@cosmos.gl/graph`` ``Graph`` from a command stream.

This is walkthru's second ecosystem adapter (after :mod:`walkthru.ecosystem.reelee`), and the
*generative* counterpart to it: where reelee maps a finished Demo Document onto a render contract,
this maps each :class:`~walkthru.core.schema.Command` onto a live cosmos.gl call so
:func:`~walkthru.core.engine.play` can choreograph a graph for screen recording. cosmos.gl already
exposes a rich **imperative, index-based** command surface on the ``Graph`` instance (camera:
``zoomToPointByIndex`` / ``fitViewByPointIndices`` / ``fitView`` / ``zoom``; live config:
``setConfigPartial``; data/colour: ``setPointColors`` / ``setLinks`` / ``setPointClusters``; sim
lifecycle: ``start`` / ``pause``), so the engine needs **zero changes** — the executor is a thin
translation to ``page.evaluate``.

**Two halves, one vocabulary.**

* *Page side* — :data:`COMMAND_CATALOG_JS` installs ``window.__cmd`` (call any ``Graph`` method by
  name) plus a few page helpers (``__startSettle`` / ``__endSettle``, and the ``__isolate`` /
  ``__restore`` / ``__recolor`` visual-fx, since ``@cosmos.gl/graph`` has no public subset-select —
  isolation is done by re-colouring non-members to near-transparent). A recording page builds its
  ``Graph`` and then calls ``window.__installCosmosglCommands(graph, ctx)``.
* *Python side* — :class:`CosmosglExecutor` translates a ``Command`` into the matching
  ``page.evaluate`` call, and the :func:`graph_command` / :func:`fx_command` / :func:`settle_start`
  / :func:`settle_end` factories author the matching :class:`~walkthru.core.schema.Command`\\ s.

**Command-id vocabulary** — ``"<namespace>.<name>"`` with positional args in ``params["args"]``:

==================  ============================  ==================================================
id                  page call                     intent
==================  ============================  ==================================================
``graph.<method>``  ``window.__cmd(method, …)``    any ``Graph`` method (camera, live config, sim)
``fx.<helper>``     ``window.__<helper>(…)``       a page visual-fx helper (``isolate``/``restore``/``recolor``)
``sim.<helper>``    ``window.__<helper>(…)``       a page sim-lifecycle helper (``startSettle``/``endSettle``)
==================  ============================  ==================================================

Like the Playwright adapters, the executor imports nothing from ``playwright`` at runtime — it
drives an injected, duck-typed ``page`` with an async ``evaluate``, so it is unit-testable with a
fake page and the core stays vendor-free.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from walkthru.core.schema import Command

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page

#: The namespaces a command id may use (the part before the first ``.``).
_GRAPH_NS = "graph"
_HELPER_NAMESPACES = frozenset({"fx", "sim"})

#: JS evaluated to dispatch a ``graph.<method>`` command to ``window.__cmd``.
_DISPATCH_CMD_JS = "(p) => window.__cmd(p.n, ...p.a)"
#: JS evaluated to dispatch an ``fx.<name>`` / ``sim.<name>`` command to ``window.__<name>``.
_DISPATCH_HELPER_JS = "(p) => window['__' + p.n](...p.a)"
#: JS that reads and clears the page's last command error (``window.__cmderr``).
_READ_CMDERR_JS = (
    "() => { const e = window.__cmderr; window.__cmderr = null; return e || null; }"
)


class CosmosglError(RuntimeError):
    """A cosmos.gl ``Graph`` call raised in the page (surfaced from ``window.__cmderr``)."""


# --------------------------------------------------------------------------------------
# Command factories — author the Commands the executor understands
# --------------------------------------------------------------------------------------


def graph_command(method: str, *args: Any) -> Command:
    """A ``graph.<method>`` command: call ``Graph.<method>(*args)`` on the live instance.

    E.g. ``graph_command("zoomToPointByIndex", hub, 2600, 7, True, False)`` or
    ``graph_command("setConfigPartial", {"simulationGravity": 0.18})``.
    """
    return Command(id=f"{_GRAPH_NS}.{method}", params={"args": list(args)})


def fx_command(helper: str, *args: Any) -> Command:
    """An ``fx.<helper>`` command: call the page visual-fx helper ``window.__<helper>(*args)``.

    The proven helpers are ``isolate`` (dim every non-member of a community), ``restore`` (back to
    the base colours), and ``recolor`` (swap to a named colour lens). See :data:`COMMAND_CATALOG_JS`.
    """
    return Command(id=f"fx.{helper}", params={"args": list(args)})


def settle_start() -> Command:
    """A ``sim.startSettle`` command: run the simulation with a gentle periodic re-fit."""
    return Command(id="sim.startSettle", params={"args": []})


def settle_end() -> Command:
    """A ``sim.endSettle`` command: stop the periodic re-fit and freeze (pause) the simulation."""
    return Command(id="sim.endSettle", params={"args": []})


# --------------------------------------------------------------------------------------
# The page-side command catalog (installed once per recording page)
# --------------------------------------------------------------------------------------

#: The reusable JS command catalog. A recording page includes this, builds its ``Graph``, then
#: calls ``window.__installCosmosglCommands(graph, ctx)`` where ``ctx`` carries the decoded typed
#: arrays the visual-fx helpers need::
#:
#:     ctx = {
#:       baseColors:   Float32Array,          // the default (community) colour lens, RGBA per point
#:       clusterCodes: Int32Array | null,     // per-point community code (for __isolate)
#:       colorSets:    { [key]: Float32Array },// alternate colour lenses (for __recolor)
#:       fitEveryMs:   number,                // re-fit cadence during settle (default 700)
#:     }
#:
#: A paused engine has no redraw loop, so every while-paused colour change is flushed with an
#: explicit ``graph.render()`` (the ``_setColors`` helper) — without it ``setPointColors`` never
#: reaches the GPU. This is the load-bearing gotcha from the prototype.
COMMAND_CATALOG_JS = r"""
window.__cmderr = null;
window.__installCosmosglCommands = (graph, ctx) => {
  ctx = ctx || {};
  const baseColors = ctx.baseColors || null;
  const clusterCodes = ctx.clusterCodes || null;
  const colorSets = ctx.colorSets || {};
  const fitEveryMs = ctx.fitEveryMs || 700;
  let fitTimer = null;
  // A paused engine has no redraw loop, so a colour change must be flushed with render().
  const setColors = (arr) => {
    try { graph.setPointColors(arr); graph.render(); }
    catch (e) { window.__cmderr = String(e); }
  };
  // The whole graph.* vocabulary in one line: call any Graph method by name.
  window.__cmd = (name, ...args) => {
    try { return graph && graph[name](...args); }
    catch (e) { window.__cmderr = String(e); }
  };
  // Settle: run the sim with a gentle periodic re-fit, then freeze it.
  window.__startSettle = () => {
    if (!graph) return;
    graph.start(1);
    fitTimer = setInterval(() => { try { graph.fitView(600, 0.14); } catch (e) {} }, fitEveryMs);
  };
  window.__endSettle = () => {
    if (fitTimer) { clearInterval(fitTimer); fitTimer = null; }
    if (graph) { try { graph.pause(); } catch (e) {} }
  };
  // Isolate a community by dimming every non-member to near-transparent (no public subset-select).
  window.__isolate = (commId) => {
    if (!graph || !clusterCodes || !baseColors) return;
    const c = baseColors.slice();
    for (let i = 0; i < clusterCodes.length; i++) {
      if (clusterCodes[i] !== commId) c[i * 4 + 3] = 0.05;
    }
    setColors(c);
  };
  window.__restore = () => { if (graph && baseColors) setColors(baseColors); };
  // Swap the colour lens (e.g. "degree" vs "community") from a precomputed set.
  window.__recolor = (key) => { const set = colorSets[key]; if (set) setColors(set); };
};
"""


# --------------------------------------------------------------------------------------
# The executor — Command -> page.evaluate
# --------------------------------------------------------------------------------------


class CosmosglExecutor:
    """An :data:`~walkthru.core.engine.Executor` (and ``CommandPlayer``) over a Playwright page.

    Construct it with a page whose document has installed :data:`COMMAND_CATALOG_JS` (via
    ``window.__installCosmosglCommands``), then pass it to :func:`~walkthru.core.engine.play` as the
    executor. Each command is translated to the matching ``page.evaluate`` call; when
    ``check_errors`` is set (default), the page's ``window.__cmderr`` is read after every call and a
    non-empty value is raised as :class:`CosmosglError` — which the engine surfaces as a
    :class:`~walkthru.core.events.CommandError` event without aborting the run.

    Args:
        page: a Playwright ``Page`` (injected, duck-typed — only an async ``evaluate`` is used).
        check_errors: read/clear ``window.__cmderr`` after each call and raise on a non-empty value.
    """

    def __init__(self, page: "Page", *, check_errors: bool = True):
        self._page = page
        self._check_errors = check_errors

    async def __call__(self, command: Command) -> Any:
        return await self.play(command)

    async def play(self, command: Command) -> Any:
        namespace, _, name = command.id.partition(".")
        if not name or (namespace != _GRAPH_NS and namespace not in _HELPER_NAMESPACES):
            raise ValueError(
                f"cosmosgl: unknown command id {command.id!r}; expected "
                f"'graph.<method>', 'fx.<helper>', or 'sim.<helper>'"
            )
        args = list((command.params or {}).get("args", ()))
        dispatch = _DISPATCH_CMD_JS if namespace == _GRAPH_NS else _DISPATCH_HELPER_JS
        result = await self._page.evaluate(dispatch, {"n": name, "a": args})
        if self._check_errors:
            err = await self._page.evaluate(_READ_CMDERR_JS)
            if err:
                raise CosmosglError(f"{command.id}: {err}")
        return result
