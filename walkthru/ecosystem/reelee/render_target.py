"""The reelee ``RenderTarget`` — map a Demo Document onto reelee's Ken Burns film contract.

This is walkthru's first real :class:`~walkthru.ports.RenderTarget` (PLAN §6, ``DECISIONS.md``
§D2). ``reelee`` is a MoviePy/ffmpeg **Ken Burns** film generator: it projects an ordered
sequence of :class:`reelee.storyboard_export.PanelView` records into one continuous pan/zoom film
(``reelee/kenburns_video.py``). This adapter is the bridge from walkthru's *representation* (the
Demo Document, composed onto absolute time by :func:`~walkthru.core.timeline.resolve_timeline`) to
that *rendering* contract.

**Why panels, not a ``reelee.Project``.** ``render_kenburns_video(project, …)`` re-derives its
panels from a ``reelee.Project`` graph (``collect_panel_views(project)``) — an ``nw``/``lacing``
annotation + content-addressed-artifact model. Reconstructing that graph just to feed back data we
already hold as a clean :class:`~walkthru.core.timeline.Timeline` would bleed reelee's whole
internal model across the firewall. Instead we map the timeline **directly** to ``PanelView``\\ s
and drive the film with the *same lower-level primitives* ``render_kenburns_video`` uses internally
— :func:`burns.ken_burns_path` for the per-panel motion and an injectable ``film_renderer``
(default :func:`reelee.kenburns_video.default_film_renderer`). Per-panel **screen time comes from
the walkthru timeline** (the SSOT already composes it), not from reelee's shot-timing strategies.

The mapping (one panel per ``CommandStep``/``Beat``):

================  ==========================================================================
``PanelView``     source
================  ==========================================================================
``index``         1-based position in document order
``panel_id``      the step id
``caption``       narration anchored to the step (joined), falling back to a ``Beat``'s text
``image_path``    the step's ``poster`` :class:`~walkthru.core.schema.AssetRef`, resolved local
``camera``        a light hint from the camera track (``push in``/``pull out``) — informational
``notes``         provenance (the command id, or the beat kind)
``shot_id``       the step id; ``framing``/``transition_in`` reserved (renderer may ignore)
================  ==========================================================================

Everything heavy (``burns``, ``reelee.kenburns_video``, ``mixing``) is imported lazily, so the
pure mapping (:func:`timeline_to_panels`) works wherever ``reelee.storyboard_export`` imports, and
a caller can inject a stub ``film_renderer`` to exercise the pipeline with no ffmpeg/MoviePy stack.
"""

from __future__ import annotations

import tempfile
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional, Union

from reelee.storyboard_export import PanelView

from walkthru.core.schema import AssetRef, DemoDocument, Rect
from walkthru.core.timeline import (
    ResolvedCamera,
    ResolvedNarration,
    ResolvedStep,
    Timeline,
    resolve_timeline,
)

#: Resolves a step ``poster`` (or narration ``audioRef``) to a local file, or ``None``.
AssetResolver = Callable[[Optional[AssetRef]], Optional[Path]]
#: Renders ``(image, BurnsPath, duration_s)`` panels (+ optional audio) into one mp4.
FilmRenderer = Callable[..., Path]
#: Assembles per-panel ``(audio, duration_s)`` into one film-long audio track (or ``None``).
AudioAssembler = Callable[..., Optional[Path]]
#: Builds the ``burns.BurnsPath`` one panel's camera follows (see :func:`index_path_builder`).
PathBuilder = Callable[["PanelPlan"], object]

DEFAULT_FPS = 30
DEFAULT_ZOOM = 1.10
DEFAULT_PAN = 0.03
DEFAULT_STYLE = "push"
#: Per-panel floor screen time (seconds) — a still that flashes by reads as a glitch.
DEFAULT_MIN_DURATION_S = 2.0


@dataclass(frozen=True)
class CameraMove:
    """One panel's camera intent in burns' vocabulary: a named move, how close, and onto what.

    Derived from the step's camera track by :func:`camera_move` — the walkthru SSOT stays a
    ``CameraKeyframe`` (focus rect + zoom); this is its projection onto the move names burns and
    braidio share (``burns.MOVES``), so a film rendered from it and a panel record written from it
    (:mod:`walkthru.ecosystem.reelee.production`) describe the same camera.
    """

    move: str
    zoom: float
    focus: Optional[Rect] = None
    easing: Optional[str] = None


#: burns' own default easing — what ``resolve_move`` uses when given none, and so what braidio's
#: render and the studio's move preview use (a panel record carries no easing).
DEFAULT_EASING = "ease-in-out"


@dataclass(frozen=True)
class Framing:
    """How a film frames its panels: one value, shared by the render and the records it writes.

    :func:`camera_path_builder` renders with it and
    :func:`~walkthru.ecosystem.reelee.production.to_production_manifest` describes the film with
    it. Passing the same :class:`Framing` to both is what keeps the panel records true to the
    pixels; two separate sets of knobs would drift apart silently.

    Args:
        default_move: the move for a panel whose step has no camera keyframe.
        aspect: the film's ``width / height``; ``None`` frames for each image's own aspect.
        device_scale_factor: pixels per CSS pixel in the posters (focus rects are CSS pixels).
        easing: used when a keyframe names none.
    """

    default_move: CameraMove = CameraMove(move="hold", zoom=1.0)
    aspect: Optional[float] = None
    device_scale_factor: float = 1.0
    easing: str = DEFAULT_EASING


@dataclass(frozen=True)
class PanelPlan:
    """A panel plus the timeline-derived screen time and narration audio for one step.

    :func:`timeline_to_panels` yields just the display-ready :class:`PanelView`; a render also
    needs *how long* each panel is on screen and *what* (if anything) plays over it — both derived
    from the same walkthru timeline. :class:`PanelPlan` carries all three so :func:`render_plans`
    needs nothing but the plan list.
    """

    view: PanelView
    duration_s: float
    audio_path: Optional[Path]
    move: Optional[CameraMove] = None


# --------------------------------------------------------------------------------------
# Default asset resolution (uri -> local Path)
# --------------------------------------------------------------------------------------


def default_asset_resolver(asset: Optional[AssetRef]) -> Optional[Path]:
    """Resolve an :class:`AssetRef` to a local file: its ``uri`` as a path, if it exists.

    The conservative default for offline rendering — a ``uri`` that is a local path resolves, and
    anything else (a remote URL, a missing file) returns ``None`` so the panel is simply rendered
    without that asset rather than failing the whole film. Inject a custom resolver (e.g. one that
    fetches remote URIs into a cache) for richer behavior.
    """
    if asset is None:
        return None
    path = Path(asset.uri)
    return path if path.exists() else None


# --------------------------------------------------------------------------------------
# The mapping: Timeline -> PanelView / PanelPlan
# --------------------------------------------------------------------------------------


def _narration_by_step(timeline: Timeline) -> dict[str, list[ResolvedNarration]]:
    by_step: dict[str, list[ResolvedNarration]] = {}
    for seg in timeline.narration:
        by_step.setdefault(seg.segment.anchor.step_id, []).append(seg)
    for segs in by_step.values():
        segs.sort(key=lambda s: s.start_ms)
    return by_step


def _camera_by_step(timeline: Timeline) -> dict[str, list[ResolvedCamera]]:
    by_step: dict[str, list[ResolvedCamera]] = {}
    for cam in timeline.camera:
        by_step.setdefault(cam.keyframe.anchor.step_id, []).append(cam)
    return by_step


def _caption(step: ResolvedStep, narration: list[ResolvedNarration]) -> str:
    text = " ".join(n.text for n in narration if n.text).strip()
    if not text and step.kind == "beat":
        text = getattr(step.step, "text", None) or ""
    return text


def _camera_hint(narration: list[ResolvedCamera]) -> str:
    for cam in narration:
        zoom = cam.keyframe.zoom
        if zoom > 1.0:
            return "push in"
        if zoom < 1.0:
            return "pull out"
    return ""


def camera_move(camera: Sequence[ResolvedCamera]) -> Optional[CameraMove]:
    """Project a step's camera keyframes onto one named move (``None`` when there are none).

    The first keyframe decides, as with :func:`_camera_hint`: ``zoom > 1`` pushes in to that
    magnification, ``zoom < 1`` pulls out from ``1 / zoom``, and ``zoom == 1`` holds still. The
    keyframe's ``focus`` (CSS pixels) is what the camera closes on. A non-positive zoom names no
    magnification and yields ``None``, as no keyframe does.

    >>> from walkthru.core.schema import Anchor, CameraKeyframe
    >>> from walkthru.core.timeline import ResolvedCamera
    >>> kf = CameraKeyframe(id="c", anchor=Anchor(step_id="s"), zoom=0.8)
    >>> camera_move([ResolvedCamera(keyframe_id="c", at_ms=0, keyframe=kf)]).move
    'pull_out'
    """
    if not camera:
        return None
    keyframe = camera[0].keyframe
    if keyframe.zoom <= 0:
        return None  # names no magnification, so no move; the default decides
    if keyframe.zoom > 1.0:
        move, zoom = "push_in", keyframe.zoom
    elif keyframe.zoom < 1.0:
        move, zoom = "pull_out", 1.0 / keyframe.zoom
    else:
        move, zoom = "hold", 1.0
    return CameraMove(move=move, zoom=zoom, focus=keyframe.focus, easing=keyframe.easing)


def normalized_focus(
    rect: Rect, image_size: tuple[int, int], *, device_scale_factor: float = 1.0
) -> tuple[float, float, float, float]:
    """A CSS-pixel ``rect`` as ``(x, y, w, h)`` fractions of an image, clamped into it.

    ``device_scale_factor`` is the capture's pixels per CSS pixel (2 on a retina screenshot).

    >>> normalized_focus(Rect(x=480, y=270, width=960, height=540), (1920, 1080))
    (0.25, 0.25, 0.5, 0.5)
    """
    width, height = image_size
    sx, sy = device_scale_factor / width, device_scale_factor / height
    x0 = min(max(rect.x * sx, 0.0), 1.0)
    y0 = min(max(rect.y * sy, 0.0), 1.0)
    x1 = min(max((rect.x + rect.width) * sx, 0.0), 1.0)
    y1 = min(max((rect.y + rect.height) * sy, 0.0), 1.0)
    return (x0, y0, x1 - x0, y1 - y0)


def _notes(step: ResolvedStep) -> str:
    if step.kind == "command":
        return f"command: {step.step.command.id}"
    return f"beat: {step.step.beat_kind}"


def _panel_view(
    step: ResolvedStep,
    index: int,
    *,
    narration: list[ResolvedNarration],
    camera: list[ResolvedCamera],
    poster_resolver: AssetResolver,
) -> PanelView:
    return PanelView(
        index=index,
        panel_id=step.step_id,
        caption=_caption(step, narration),
        shot_id=step.step_id,
        framing="",
        camera=_camera_hint(camera),
        transition_in="",
        notes=_notes(step),
        image_path=poster_resolver(step.step.poster),
    )


def timeline_to_panels(
    timeline: Timeline,
    *,
    poster_resolver: AssetResolver = default_asset_resolver,
) -> list[PanelView]:
    """Project a resolved :class:`~walkthru.core.timeline.Timeline` into ordered ``PanelView``\\ s.

    One panel per step (``CommandStep``/``Beat``), in document order. This is the pure heart of the
    adapter — no rendering, no I/O beyond ``poster_resolver`` — so it is fully unit-testable. A
    panel whose ``poster`` does not resolve gets ``image_path=None``; :func:`render_plans` drops
    such panels (a Ken Burns film needs an image), exactly as reelee's own pipeline does.
    """
    narration = _narration_by_step(timeline)
    camera = _camera_by_step(timeline)
    return [
        _panel_view(
            step,
            index,
            narration=narration.get(step.step_id, []),
            camera=camera.get(step.step_id, []),
            poster_resolver=poster_resolver,
        )
        for index, step in enumerate(timeline.steps, start=1)
    ]


def _panel_audio(
    narration: list[ResolvedNarration], audio_resolver: AssetResolver
) -> Optional[Path]:
    """The first resolvable narration audio for a step (MVP: one audio clip per panel)."""
    for seg in narration:
        path = audio_resolver(seg.segment.audio_ref)
        if path is not None:
            return path
    return None


def timeline_to_plans(
    timeline: Timeline,
    *,
    poster_resolver: AssetResolver = default_asset_resolver,
    audio_resolver: AssetResolver = default_asset_resolver,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
) -> list[PanelPlan]:
    """Project the timeline into renderable :class:`PanelPlan`\\ s (panel + screen time + audio).

    Screen time for a step is its full timeline occupancy — ``durationMs`` plus any
    ``holdAfterMs`` — in seconds, floored at ``min_duration_s`` so no panel flashes by. Audio is
    the step's first resolvable narration ``audioRef``. Both come straight from the walkthru SSOT;
    reelee's shot-timing strategies are deliberately *not* used (walkthru already owns timing).
    """
    narration = _narration_by_step(timeline)
    camera = _camera_by_step(timeline)
    plans: list[PanelPlan] = []
    for index, step in enumerate(timeline.steps, start=1):
        segs = narration.get(step.step_id, [])
        occupancy_s = (step.end_ms - step.start_ms + step.hold_after_ms) / 1000.0
        plans.append(
            PanelPlan(
                view=_panel_view(
                    step,
                    index,
                    narration=segs,
                    camera=camera.get(step.step_id, []),
                    poster_resolver=poster_resolver,
                ),
                duration_s=max(min_duration_s, occupancy_s),
                audio_path=_panel_audio(segs, audio_resolver),
                move=camera_move(camera.get(step.step_id, [])),
            )
        )
    return plans


# --------------------------------------------------------------------------------------
# The render: PanelPlan[] -> mp4, via burns + an injectable film renderer
# --------------------------------------------------------------------------------------


def _default_film_renderer() -> FilmRenderer:
    from reelee.kenburns_video import default_film_renderer

    return default_film_renderer


def _default_audio_assembler() -> AudioAssembler:
    from mixing import assemble_audio_track

    return assemble_audio_track


def index_path_builder(
    *,
    style: str = DEFAULT_STYLE,
    zoom: float = DEFAULT_ZOOM,
    pan: float = DEFAULT_PAN,
    easing: str = "linear",
) -> PathBuilder:
    """The default motion: :func:`burns.ken_burns_path` by panel position, ignoring the camera track.

    Every panel gets the same ``style``/``zoom``/``pan``, varied only by its index — what this
    target has always rendered. Use :func:`camera_path_builder` for motion the document authors.
    """
    from burns import ken_burns_path

    def build(plan: PanelPlan):
        return ken_burns_path(plan.view.index, style=style, zoom=zoom, pan=pan, easing=easing)

    return build


def camera_path_builder(framing: Framing = Framing()) -> PathBuilder:
    """Motion from the document's camera track, resolved by :func:`burns.resolve_move`.

    Each panel's :class:`CameraMove` (see :func:`camera_move`) is framed against its own image —
    the focus rect closes the camera on the element a step is about. ``resolve_move`` is the one
    resolver braidio's ``video_cut.render`` and the studio's move preview also call, so a panel
    record carrying the same move/zoom/focus describes exactly this film
    (:func:`walkthru.ecosystem.reelee.production.to_production_manifest`, given the same
    ``framing``, writes those records).
    """
    from burns import resolve_move
    from PIL import Image

    def build(plan: PanelPlan):
        intent = plan.move or framing.default_move
        focus = None
        if intent.focus is not None:
            with Image.open(plan.view.image_path) as img:
                size = img.size
            focus = normalized_focus(
                intent.focus, size, device_scale_factor=framing.device_scale_factor
            )
        return resolve_move(
            intent.move,
            image=plan.view.image_path,
            aspect=framing.aspect,
            zoom=intent.zoom,
            focus=focus,
            easing=intent.easing or framing.easing,
        )

    return build


def render_plans(
    plans: Sequence[PanelPlan],
    out: Union[str, Path],
    *,
    fps: int = DEFAULT_FPS,
    zoom: float = DEFAULT_ZOOM,
    pan: float = DEFAULT_PAN,
    style: str = DEFAULT_STYLE,
    ease: bool = False,
    film_renderer: Optional[FilmRenderer] = None,
    audio_assembler: Optional[AudioAssembler] = None,
    path_builder: Optional[PathBuilder] = None,
    audio_out: Optional[Union[str, Path]] = None,
) -> Path:
    """Render ``plans`` into one continuous Ken Burns mp4 at ``out``.

    Mirrors the panel→film body of :func:`reelee.kenburns_video.render_kenburns_video` but consumes
    walkthru's own panels and timing rather than a ``reelee.Project``: a :func:`burns.ken_burns_path`
    per panel, an optional film-long audio track assembled from per-panel narration, and one
    ``film_renderer`` call. ``film_renderer`` and ``audio_assembler`` are injected (defaulting to
    reelee/mixing) so the whole pipeline runs with a stub and no ffmpeg/MoviePy.

    Args:
        plans: the panels to render, in order (see :func:`timeline_to_plans`).
        out: target mp4 path (parent dirs created on demand).
        fps: frames per second of the rendered film.
        zoom: zoomed-end scale for the ``push`` style.
        pan: how far the framing drifts off-center, in ``[0, 1]``.
        style: ``"push"`` (cinematic push) or ``"drift"`` (pure horizontal pan).
        ease: ``True`` for slow-in/slow-out easing, ``False`` for constant velocity.
        film_renderer: renders the panels (+ optional audio) into one mp4; injected for testing.
        audio_assembler: assembles per-panel audio into one track; injected for testing.
        path_builder: the camera strategy, ``PanelPlan -> BurnsPath``. ``None`` is
            :func:`index_path_builder` over ``style``/``zoom``/``pan``/``ease``;
            :func:`camera_path_builder` follows the document's camera track instead. Given one,
            ``style``/``zoom``/``pan``/``ease`` are not used: the builder carries its own.
        audio_out: keep the assembled film-long audio here (by default it is a temporary file).
            A caller that ships the film's recording beside it (a commentary production) needs it.

    Returns:
        The path to the written mp4.

    Raises:
        ValueError: when no panel has a resolvable image (a Ken Burns film needs panel images).
    """
    out_path = Path(out)
    renderable = [p for p in plans if p.view.image_path is not None]
    if not renderable:
        raise ValueError(
            "reelee render target: no panel has a resolvable poster image — a Ken Burns "
            "film needs panel images (give steps a `poster` AssetRef that resolves locally)."
        )
    film_renderer = film_renderer or _default_film_renderer()
    path_builder = path_builder or index_path_builder(
        style=style, zoom=zoom, pan=pan, easing="ease-in-out" if ease else "linear"
    )
    panels = [
        (plan.view.image_path, path_builder(plan), plan.duration_s)
        for plan in renderable
    ]
    audio_segments = [(plan.audio_path, plan.duration_s) for plan in renderable]
    out_path.parent.mkdir(parents=True, exist_ok=True)
    if not any(audio is not None for audio, _ in audio_segments):
        film_renderer(panels, saveas=out_path, fps=fps, audio_path=None)
        return out_path
    assembler = audio_assembler or _default_audio_assembler()
    if audio_out is not None:
        Path(audio_out).parent.mkdir(parents=True, exist_ok=True)
        audio_path = assembler(audio_segments, output=Path(audio_out))
        film_renderer(panels, saveas=out_path, fps=fps, audio_path=audio_path)
        return out_path
    with tempfile.TemporaryDirectory(prefix="walkthru_reelee_") as tmp:
        audio_path = assembler(audio_segments, output=Path(tmp) / "film_audio.wav")
        film_renderer(panels, saveas=out_path, fps=fps, audio_path=audio_path)
    return out_path


def render_demo_video(
    document: DemoDocument,
    out: Union[str, Path],
    *,
    poster_resolver: AssetResolver = default_asset_resolver,
    audio_resolver: AssetResolver = default_asset_resolver,
    min_duration_s: float = DEFAULT_MIN_DURATION_S,
    fps: int = DEFAULT_FPS,
    zoom: float = DEFAULT_ZOOM,
    pan: float = DEFAULT_PAN,
    style: str = DEFAULT_STYLE,
    ease: bool = False,
    film_renderer: Optional[FilmRenderer] = None,
    audio_assembler: Optional[AudioAssembler] = None,
    path_builder: Optional[PathBuilder] = None,
    audio_out: Optional[Union[str, Path]] = None,
) -> Path:
    """Compose ``document`` onto absolute time and render it as a Ken Burns mp4 at ``out``.

    The one-call driver: :func:`~walkthru.core.timeline.resolve_timeline` →
    :func:`timeline_to_plans` → :func:`render_plans`. See those for the per-argument detail.
    """
    timeline = resolve_timeline(document)
    plans = timeline_to_plans(
        timeline,
        poster_resolver=poster_resolver,
        audio_resolver=audio_resolver,
        min_duration_s=min_duration_s,
    )
    return render_plans(
        plans,
        out,
        fps=fps,
        zoom=zoom,
        pan=pan,
        style=style,
        ease=ease,
        film_renderer=film_renderer,
        audio_assembler=audio_assembler,
        path_builder=path_builder,
        audio_out=audio_out,
    )


class ReeleeRenderTarget:
    """A :class:`~walkthru.ports.RenderTarget` that renders a Demo Document to a Ken Burns mp4.

    Writes ``<document.id>.mp4`` into ``out_dir`` (mirroring
    :class:`~walkthru.adapters.export.json_target.JsonArtifactTarget`). All render knobs are set at
    construction; :meth:`export` then takes just the artifact, satisfying the port's narrow
    signature. ``film_renderer``/``audio_assembler`` are injectable for testing.

    Args:
        out_dir: directory to write the mp4 into (created on demand).
        fps, zoom, pan, style, ease, min_duration_s: render knobs (see :func:`render_plans` /
            :func:`timeline_to_plans`).
        poster_resolver, audio_resolver: map an :class:`AssetRef` to a local file.
        film_renderer, audio_assembler: injected render seams (default reelee/mixing).
        path_builder: the camera strategy (see :func:`render_plans`).
    """

    def __init__(
        self,
        out_dir: Union[str, Path] = ".",
        *,
        fps: int = DEFAULT_FPS,
        zoom: float = DEFAULT_ZOOM,
        pan: float = DEFAULT_PAN,
        style: str = DEFAULT_STYLE,
        ease: bool = False,
        min_duration_s: float = DEFAULT_MIN_DURATION_S,
        poster_resolver: AssetResolver = default_asset_resolver,
        audio_resolver: AssetResolver = default_asset_resolver,
        film_renderer: Optional[FilmRenderer] = None,
        audio_assembler: Optional[AudioAssembler] = None,
        path_builder: Optional[PathBuilder] = None,
    ):
        self._out_dir = Path(out_dir)
        self._path_builder = path_builder
        self._fps = fps
        self._zoom = zoom
        self._pan = pan
        self._style = style
        self._ease = ease
        self._min_duration_s = min_duration_s
        self._poster_resolver = poster_resolver
        self._audio_resolver = audio_resolver
        self._film_renderer = film_renderer
        self._audio_assembler = audio_assembler

    async def export(self, artifact: DemoDocument) -> AssetRef:
        out_path = self._out_dir / f"{artifact.id}.mp4"
        render_demo_video(
            artifact,
            out_path,
            poster_resolver=self._poster_resolver,
            audio_resolver=self._audio_resolver,
            min_duration_s=self._min_duration_s,
            fps=self._fps,
            zoom=self._zoom,
            pan=self._pan,
            style=self._style,
            ease=self._ease,
            film_renderer=self._film_renderer,
            audio_assembler=self._audio_assembler,
            path_builder=self._path_builder,
        )
        return AssetRef(uri=str(out_path), mime="video/mp4")
