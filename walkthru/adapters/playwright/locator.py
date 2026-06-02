"""Playwright ``ElementLocator`` — resolve a resilient ``Target`` to live viewport geometry.

walkthru's first real :class:`~walkthru.ports.ElementLocator` (PLAN §3.4). A
:class:`~walkthru.core.schema.Target` is a *prioritized* locator: try ``primary``, then each of
``fallbacks`` in order, and only then the record-time ``bbox`` the Target explicitly carries as a
last resort. The first candidate that resolves to a visible element wins; its Playwright
``bounding_box()`` becomes the returned :class:`~walkthru.core.schema.Rect`.

**Firewall.** This adapter imports nothing from ``playwright`` at runtime — it drives an injected,
duck-typed Playwright ``Page`` (anything whose ``get_by_role`` / ``get_by_test_id`` / ``locator`` /
… return objects exposing ``count()`` and ``first.bounding_box()``). So the core stays vendor-free,
the ``playwright`` extra is needed only to *construct* a real page, and the adapter is unit-testable
with an in-memory fake. This mirrors the lazy-``reelee`` discipline of
:mod:`walkthru.ecosystem.reelee`.

**Guardrail (#6, ``reserve-don't-build``).** Falling back to ``Target.bbox`` is *not* self-healing
— it is using the geometry the SSOT deliberately captured at record time for exactly this case.
Re-resolving a *drifted* locator into a new SSOT entry must remain a human-reviewed suggestion and
is out of scope here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Optional

from walkthru.core.schema import Locator, Rect, Target

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page


class ElementNotFoundError(LookupError):
    """No locator (``primary``, any ``fallback``, or the record-time ``bbox``) resolved a target."""

    def __init__(self, target: Target):
        self.target = target
        tried = ", ".join(
            f"{loc.strategy}={loc.value!r}"
            for loc in (target.primary, *target.fallbacks)
        )
        super().__init__(
            f"could not resolve any locator for target (tried: {tried}), and no "
            f"record-time bbox was available as a last resort"
        )


def _build_locator(page: Any, loc: Locator) -> Any:
    """Map a schema :class:`~walkthru.core.schema.Locator` onto a Playwright locator.

    Prefers Playwright's semantic getters (role / test-id / text / label) over raw CSS/XPath,
    matching the schema's own ordering bias toward resilient strategies.
    """
    if loc.strategy == "role":
        return page.get_by_role(loc.value, name=loc.name)
    if loc.strategy == "testid":
        return page.get_by_test_id(loc.value)
    if loc.strategy == "text":
        return page.get_by_text(loc.value)
    if loc.strategy == "label":
        return page.get_by_label(loc.value)
    if loc.strategy == "css":
        return page.locator(loc.value)
    if loc.strategy == "xpath":
        return page.locator(f"xpath={loc.value}")
    # Unreachable: ``strategy`` is a schema ``Literal`` validated at construction.
    raise ValueError(f"unknown locator strategy: {loc.strategy!r}")


class PlaywrightElementLocator:
    """A :class:`~walkthru.ports.ElementLocator` backed by Playwright ``bounding_box()``.

    Args:
        page: a Playwright ``Page`` (injected, duck-typed — see the module docstring).
    """

    def __init__(self, page: "Page"):
        self._page = page

    async def bounds(self, target: Target) -> Rect:
        """Resolve ``target`` to a viewport :class:`~walkthru.core.schema.Rect`.

        Tries ``primary`` then each ``fallback`` in order; the first that resolves to an element
        with a bounding box wins. If none resolve, returns the record-time ``Target.bbox`` when
        present, else raises :class:`ElementNotFoundError`.
        """
        for loc in (target.primary, *target.fallbacks):
            rect = await self._resolve(loc)
            if rect is not None:
                return rect
        if target.bbox is not None:
            return target.bbox
        raise ElementNotFoundError(target)

    async def _resolve(self, loc: Locator) -> Optional[Rect]:
        """The Playwright geometry for ``loc``, or ``None`` if it matches nothing visible.

        Uses ``count()`` (which returns immediately) to skip non-matching candidates rather than
        letting ``bounding_box()`` block on its auto-wait timeout — so fallbacks are cheap to try.
        """
        pw_locator = _build_locator(self._page, loc)
        if await pw_locator.count() == 0:
            return None
        box = await pw_locator.first.bounding_box()
        if not box:  # ``None`` (not visible) or an empty mapping
            return None
        return Rect(x=box["x"], y=box["y"], width=box["width"], height=box["height"])
