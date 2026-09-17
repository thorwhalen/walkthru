"""Playwright ``CommandPlayer`` — run a Demo Document's commands against a real page.

The Python-side counterpart to the TS ``acture`` player. Until now the Playwright adapters
could *locate*, *wait* and *record*, but nothing could **act**: a Demo Document could
describe a browser demo and walkthru could not play it without an app-specific executor.
This closes that gap for the commonest case -- driving a web page directly.

Commands stay vendor-neutral (``Command(id, params)``); the mapping from an id to a page
operation lives in :data:`PAGE_COMMANDS`, which is a keyword argument, so an app with its
own command vocabulary reuses the player and supplies its own table.

Like the other Playwright adapters this imports nothing from ``playwright`` at runtime --
it drives an injected, duck-typed page -- so it is unit-testable with a fake.

>>> import asyncio
>>> class FakePage:
...     def __init__(self): self.calls = []
...     async def goto(self, url, **kw): self.calls.append(("goto", url))
...     async def hover(self, sel, **kw): self.calls.append(("hover", sel))
>>> page = FakePage()
>>> player = PlaywrightCommandPlayer(page)
>>> from walkthru.core.schema import Command
>>> asyncio.run(player.play(Command(id="page.goto", params={"url": "https://example.org"})))
>>> asyncio.run(player.play(Command(id="page.hover", params={"selector": "mark"})))
>>> page.calls
[('goto', 'https://example.org'), ('hover', 'mark')]
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Awaitable, Callable, Mapping, Optional

from walkthru.core.schema import Command

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page

__all__ = [
    "UnknownCommandError",
    "PAGE_COMMANDS",
    "PlaywrightCommandPlayer",
]

Handler = Callable[[Any, Mapping[str, Any]], Awaitable[Any]]


class UnknownCommandError(KeyError):
    """The command id has no handler in this player's table."""


async def _goto(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.goto(p["url"], **{k: v for k, v in p.items() if k != "url"})


async def _hover(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.hover(p["selector"], **_rest(p, "selector"))


async def _click(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.click(p["selector"], **_rest(p, "selector"))


async def _fill(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.fill(
        p["selector"], p.get("text", ""), **_rest(p, "selector", "text")
    )


async def _press(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.keyboard.press(p["key"])


async def _move(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.mouse.move(float(p["x"]), float(p["y"]), **_rest(p, "x", "y"))


async def _scroll(page: Any, p: Mapping[str, Any]) -> Any:
    """Scroll the window, or an element into view when a selector is given."""
    if p.get("selector"):
        return await page.locator(p["selector"]).scroll_into_view_if_needed()
    return await page.evaluate(
        "([x, y]) => window.scrollBy({left: x, top: y, behavior: 'smooth'})",
        [p.get("x", 0), p.get("y", 0)],
    )


async def _evaluate(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.evaluate(p["expression"], p.get("arg"))


async def _wait(page: Any, p: Mapping[str, Any]) -> None:
    """Idle for ``ms``. The engine paces steps; this is for a pause *inside* one."""
    await asyncio.sleep(float(p.get("ms", 0)) / 1000)


async def _wait_for(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.wait_for_selector(p["selector"], **_rest(p, "selector"))


async def _set_viewport(page: Any, p: Mapping[str, Any]) -> Any:
    return await page.set_viewport_size(
        {"width": int(p["width"]), "height": int(p["height"])}
    )


def _rest(params: Mapping[str, Any], *drop: str) -> dict:
    return {k: v for k, v in params.items() if k not in drop}


#: The default command vocabulary. A keyword argument on the player, not a global.
PAGE_COMMANDS: Mapping[str, Handler] = {
    "page.goto": _goto,
    "page.hover": _hover,
    "page.click": _click,
    "page.fill": _fill,
    "page.press": _press,
    "page.mouse.move": _move,
    "page.scroll": _scroll,
    "page.evaluate": _evaluate,
    "page.wait": _wait,
    "page.wait_for": _wait_for,
    "page.set_viewport": _set_viewport,
}


class PlaywrightCommandPlayer:
    """A :class:`~walkthru.ports.CommandPlayer` that runs commands against a page.

    Args:
        page: an injected, duck-typed Playwright ``Page``.
        commands: the id -> handler table; defaults to :data:`PAGE_COMMANDS`. Pass
            ``{**PAGE_COMMANDS, "app.save": my_handler}`` to extend rather than replace.
        on_unknown: what to do with an id the table does not have. The default raises,
            because a silently skipped command produces a demo that is wrong in a way
            nobody notices until they watch the video.

    >>> PlaywrightCommandPlayer(object()).known  # doctest: +ELLIPSIS
    ('page.click', 'page.evaluate', 'page.fill', ...)
    """

    def __init__(
        self,
        page: "Page",
        *,
        commands: Optional[Mapping[str, Handler]] = None,
        on_unknown: str = "raise",
    ):
        self._page = page
        self._commands = dict(PAGE_COMMANDS if commands is None else commands)
        if on_unknown not in ("raise", "skip"):
            raise ValueError("on_unknown must be 'raise' or 'skip'")
        self._on_unknown = on_unknown

    @property
    def known(self) -> tuple[str, ...]:
        """The command ids this player can run."""
        return tuple(sorted(self._commands))

    async def play(self, command: Command) -> Any:
        handler = self._commands.get(command.id)
        if handler is None:
            if self._on_unknown == "skip":
                return None
            raise UnknownCommandError(
                f"no handler for command {command.id!r}; known: {', '.join(self.known)}"
            )
        return await handler(self._page, dict(command.params or {}))
