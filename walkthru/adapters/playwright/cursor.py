"""A synthetic cursor overlay — because a screencast records no mouse pointer.

Playwright's screencast (and every OS-level browser capture) omits the cursor, so a demo
whose whole point is *"hover this and watch what happens"* records as a tooltip appearing
for no visible reason. The schema has had :class:`~walkthru.core.schema.CursorCue` since
the first draft; this is the Python-side renderer for it.

:func:`install_synthetic_cursor` injects a small overlay that follows the real pointer, so
the recording shows the motion that caused each effect. It is an *init script*, so it
survives navigation and is in place before the first frame.

The overlay is inert: ``pointer-events: none``, fixed position, and a z-index above
anything the page is likely to use, so it cannot change what the demo is demonstrating.

>>> js = cursor_script(size=24)
>>> "pointer-events: none" in js and "mousemove" in js
True
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:  # type-checker only — never imported at runtime (firewall)
    from playwright.async_api import Page

__all__ = [
    "CURSOR_SHAPES",
    "DEFAULT_CURSOR_SIZE",
    "cursor_script",
    "install_synthetic_cursor",
]

DEFAULT_CURSOR_SIZE = 22
#: ``arrow`` is a mouse pointer; ``touch`` is a fingertip, for a phone-sized recording where an
#: arrow would say "desktop" (make it bigger: ``size=40`` reads as a finger).
CURSOR_SHAPES = ("arrow", "touch")

# An arrow drawn as an SVG, carried base64 so the data URI contains no quote characters.
# A raw `utf8,<svg xmlns='http://...'>` URI terminates the surrounding JavaScript string
# literal at its first apostrophe and the whole init script silently fails to parse --
# silently, because an init script that throws leaves no mark on the page or the video.
_ARROW = "data:image/svg+xml;base64,PHN2ZyB4bWxucz0naHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmcnIHZpZXdCb3g9JzAgMCAyNCAyNCc+PHBhdGggZD0nTTUgMiBMNSAyMCBMMTAgMTUuNSBMMTMgMjIgTDE2IDIwLjUgTDEzIDE0LjUgTDE5LjUgMTQgWicgZmlsbD0nd2hpdGUnIHN0cm9rZT0nYmxhY2snIHN0cm9rZS13aWR0aD0nMS41JyBzdHJva2UtbGluZWpvaW49J3JvdW5kJy8+PC9zdmc+"


def cursor_script(
    *,
    size: int = DEFAULT_CURSOR_SIZE,
    smoothing_ms: int = 90,
    ring: bool = True,
    shape: str = "arrow",
) -> str:
    """The JavaScript that draws and moves the overlay.

    Args:
        size: cursor height in CSS pixels. Larger than a real pointer on purpose -- a
            22px arrow is what stays legible once a 960px capture is scaled into a GIF.
        smoothing_ms: CSS transition on the overlay's position. Playwright's mouse jumps
            between points; a short transition turns each jump into a visible glide, which
            is what makes the motion readable.
        ring: draw a contrasting halo on mouse-down, so clicks are visible too.
        shape: ``"arrow"`` (a mouse pointer, its tip on the point) or ``"touch"`` (a translucent
            fingertip centred on the point, which darkens while pressed).

    >>> "border-radius:50%" in cursor_script(shape="touch").split("walkthru-cursor-ring")[0]
    True
    >>> cursor_script(shape="hand")
    Traceback (most recent call last):
    ...
    ValueError: shape must be one of ('arrow', 'touch'), got 'hand'
    """
    if shape not in CURSOR_SHAPES:
        raise ValueError(f"shape must be one of {CURSOR_SHAPES}, got {shape!r}")
    if shape == "touch":
        look = (
            "'border-radius:50%', 'background:rgba(255,255,255,.55)', "
            "'border:2px solid rgba(0,0,0,.35)', 'box-sizing:border-box'"
        )
        offset = size / 2
        press = """
    addEventListener('mousedown', () => {{ c.style.background = 'rgba(80,80,80,.55)'; }}, {{passive: true}});
    addEventListener('mouseup', () => {{ c.style.background = 'rgba(255,255,255,.55)'; }}, {{passive: true}});"""
    else:
        look = f"'background:url(\"{_ARROW}\") no-repeat center/contain'"
        offset = 2
        press = ""
    return f"""
(() => {{
  if (window.__walkthruCursor) return;
  window.__walkthruCursor = true;
  const add = () => {{
    const c = document.createElement('div');
    c.id = 'walkthru-cursor';
    c.style.cssText = [
      'position:fixed', 'left:0', 'top:0', 'width:{size}px', 'height:{size}px',
      {look},
      'pointer-events: none', 'z-index:2147483647', 'opacity:0',
      'transform:translate(-{offset}px,-{offset}px)',
      'transition:transform {
        smoothing_ms
    }ms cubic-bezier(.22,.61,.36,1), opacity 160ms',
      'filter:drop-shadow(0 1px 2px rgba(0,0,0,.45))',
    ].join(';');
    document.body.appendChild(c);

    const r = document.createElement('div');
    r.id = 'walkthru-cursor-ring';
    r.style.cssText = [
      'position:fixed', 'left:0', 'top:0', 'width:{size * 2}px', 'height:{size * 2}px',
      'border-radius:50%', 'border:2px solid rgba(255,255,255,.9)',
      'box-shadow:0 0 0 2px rgba(0,0,0,.35)', 'pointer-events: none',
      'z-index:2147483646', 'opacity:0', 'transform:translate(-50%,-50%) scale(.4)',
      'transition:opacity 260ms, transform 260ms',
    ].join(';');
    document.body.appendChild(r);

    let shown = false;
    addEventListener('mousemove', (e) => {{
      c.style.transform = `translate(${{e.clientX - {offset}}}px, ${{e.clientY - {
        offset
    }}}px)`;
      r.style.left = e.clientX + 'px';
      r.style.top = e.clientY + 'px';
      if (!shown) {{ shown = true; c.style.opacity = '1'; }}
    }}, {{passive: true}});
{press.format() if press else ""}

    {
        '''addEventListener('mousedown', () => {
      r.style.opacity = '1'; r.style.transform = 'translate(-50%,-50%) scale(1)';
      setTimeout(() => { r.style.opacity = '0';
                         r.style.transform = 'translate(-50%,-50%) scale(.4)'; }, 260);
    }, {passive: true});'''
        if ring
        else ""
    }
  }};
  if (document.body) add();
  else addEventListener('DOMContentLoaded', add);
}})();
"""


async def install_synthetic_cursor(
    page: "Page",
    *,
    size: int = DEFAULT_CURSOR_SIZE,
    smoothing_ms: int = 90,
    ring: bool = True,
    shape: str = "arrow",
) -> Any:
    """Install the overlay on ``page``. Call before navigating.

    Duck-typed on ``page`` (no ``playwright`` import), so it is testable with a fake.

    >>> import asyncio
    >>> class FakePage:
    ...     def __init__(self): self.scripts = []
    ...     async def add_init_script(self, script): self.scripts.append(script)
    >>> page = FakePage()
    >>> asyncio.run(install_synthetic_cursor(page))
    >>> len(page.scripts), "walkthru-cursor" in page.scripts[0]
    (1, True)
    """
    return await page.add_init_script(
        cursor_script(size=size, smoothing_ms=smoothing_ms, ring=ring, shape=shape)
    )
