"""cosmos.gl ecosystem adapter — drive a live ``@cosmos.gl/graph`` graph from a command stream.

The *generative* ecosystem adapter (the counterpart to :mod:`walkthru.ecosystem.reelee`'s render
target): :class:`~walkthru.ecosystem.cosmosgl.executor.CosmosglExecutor` translates each
:class:`~walkthru.core.schema.Command` into a ``page.evaluate`` call on cosmos.gl's imperative
``Graph`` surface, so :func:`~walkthru.core.engine.play` can choreograph a graph for screen
recording. :data:`~walkthru.ecosystem.cosmosgl.executor.COMMAND_CATALOG_JS` is the page-side half
(the ``window.__cmd`` dispatcher + visual-fx helpers), and :func:`~walkthru.ecosystem.cosmosgl.executor.graph_command`
/ :func:`~walkthru.ecosystem.cosmosgl.executor.fx_command` / :func:`~walkthru.ecosystem.cosmosgl.executor.settle_start`
/ :func:`~walkthru.ecosystem.cosmosgl.executor.settle_end` author the matching commands.

Like the Playwright adapters, nothing here imports ``playwright`` at runtime — the executor drives
an injected, duck-typed page — so the core firewall holds and cosmos.gl recording stays an optional
concern of the caller (which also owns the actual screen capture). See
:mod:`walkthru.ecosystem.cosmosgl.executor` for the full design.
"""

from walkthru.ecosystem.cosmosgl.executor import (
    COMMAND_CATALOG_JS,
    CosmosglError,
    CosmosglExecutor,
    fx_command,
    graph_command,
    settle_end,
    settle_start,
)

__all__ = [
    "COMMAND_CATALOG_JS",
    "CosmosglError",
    "CosmosglExecutor",
    "fx_command",
    "graph_command",
    "settle_end",
    "settle_start",
]
