"""reelee ecosystem adapter — the first ``RenderTarget`` (Demo Document → Ken Burns mp4).

The optional bridge from walkthru's representation to ``reelee``'s MoviePy/ffmpeg Ken Burns film
contract. :class:`ReeleeRenderTarget` is the :class:`~walkthru.ports.RenderTarget`;
:func:`timeline_to_panels` is the pure mapping at its heart, and :func:`render_demo_video` /
:func:`render_plans` are the render drivers (with injectable ``film_renderer`` for testing). See
:mod:`walkthru.ecosystem.reelee.render_target` for the full design, and ``DECISIONS.md`` §D2.

Importing this module imports ``reelee``; like everything in :mod:`walkthru.ecosystem`, nothing in
the core imports it, so the firewall holds and ``reelee`` stays an optional extra.
"""

from walkthru.ecosystem.reelee.render_target import (
    AssetResolver,
    AudioAssembler,
    FilmRenderer,
    PanelPlan,
    ReeleeRenderTarget,
    default_asset_resolver,
    render_demo_video,
    render_plans,
    timeline_to_panels,
    timeline_to_plans,
)

__all__ = [
    "AssetResolver",
    "AudioAssembler",
    "FilmRenderer",
    "PanelPlan",
    "ReeleeRenderTarget",
    "default_asset_resolver",
    "render_demo_video",
    "render_plans",
    "timeline_to_panels",
    "timeline_to_plans",
]
