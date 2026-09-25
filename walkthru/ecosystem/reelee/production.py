"""A rendered Demo Document as a **commentary production** — the manifest braidio imports.

The Ken Burns film this package renders (:mod:`walkthru.ecosystem.reelee.render_target`) is
already a commentary film in every structural sense: pictures (the step posters) over a spoken
recording (the narration), each held for a span with a camera move. Reelee's studio edits exactly
that shape, and it takes a finished one in through ``braidio.importing`` — a
``ProductionManifest`` of stills, panels, narration beats and the delivered cut.
:func:`to_production_manifest` writes that manifest from the **same** :class:`PanelPlan` list the
film was rendered from, so the panel spans, moves and narration timings the studio shows are the
film's own, not a second estimate of them:

- a panel's ``start``/``end`` is the running sum of plan durations — how the film lays them out;
- its ``move``/``zoom``/``focus`` is the plan's :class:`CameraMove`, the intent
  :func:`camera_path_builder` handed to ``burns.resolve_move`` (the resolver braidio's own
  render and the studio's move preview call). Render with a different ``path_builder`` and these
  records describe a film you did not make — so this function refuses to guess: a plan without a
  move is written as ``default_move``, which must be the one the render used;
- a narration beat starts where its panel starts, which is where the audio assembler put it.

The manifest is a plain ``dict`` in braidio's wire shape; nothing here imports braidio, so the
projection is testable anywhere ``reelee`` imports. Validate and import it with
``braidio.importing.load_manifest`` / ``import_production``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from pathlib import Path
from typing import Any, Optional, Union

from walkthru.ecosystem.reelee.render_target import (
    CameraMove,
    PanelPlan,
    normalized_focus,
)

#: What a still record says about one panel's poster: ``labelled``/``subject``/``title``/...
StillFields = Callable[[PanelPlan], Mapping[str, Any]]

#: A narration beat's timeline snippet is display-only; braidio's own snippets are this long.
DEFAULT_LABEL_CHARS = 48


def _default_still_fields(plan: PanelPlan) -> Mapping[str, Any]:
    """A screenshot names nobody unless the caller says what it shows."""
    return {"labelled": False}


def _relative(path: Union[str, Path], root: Path) -> str:
    """``path`` relative to ``root``, refusing anything outside it (a manifest stores no absolutes)."""
    resolved = Path(path).resolve()
    try:
        return resolved.relative_to(root).as_posix()
    except ValueError:
        raise ValueError(
            f"{resolved} is not under the production's source_dir {root}; a manifest stores "
            "paths relative to it, never absolute ones"
        ) from None


def _image_size(path: Path) -> tuple[int, int]:
    from PIL import Image

    with Image.open(path) as img:
        return img.size


def _media_duration_s(path: Path) -> float:
    from mixing.audio import Audio

    return float(Audio(str(path)).full_duration)


def _label(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def to_production_manifest(
    plans: Sequence[PanelPlan],
    *,
    production: str,
    title: str,
    source_dir: Union[str, Path],
    film: Union[str, Path],
    audio: Union[str, Path],
    rights: Mapping[str, str],
    size: tuple[int, int],
    fps: int,
    default_move: CameraMove = CameraMove(move="hold", zoom=1.0),
    device_scale_factor: float = 1.0,
    still_fields: StillFields = _default_still_fields,
    voice: Optional[Mapping[str, str]] = None,
    cut_label: str = "v1",
    settings: Optional[Mapping[str, Any]] = None,
    gaps: Sequence[str] = (),
    duration_s: Callable[[Path], float] = _media_duration_s,
    image_size: Callable[[Path], tuple[int, int]] = _image_size,
    label_chars: int = DEFAULT_LABEL_CHARS,
) -> dict[str, Any]:
    """The braidio ``ProductionManifest`` (as a dict) for a film rendered from ``plans``.

    Args:
        plans: the panel plans the film was rendered from (:func:`timeline_to_plans`).
        production: the slug — the import's identity namespace.
        title: the production's human title.
        source_dir: the folder every file lives under; the manifest's ``source_dir`` is ``"."``,
            so import with ``source_root=source_dir``.
        film: the delivered mp4.
        audio: the film-long recording (``render_plans(..., audio_out=...)``).
        rights: braidio's ``RightsPosition``: ``position`` (private | unlisted | public), ``why``,
            and optionally ``measured``.
        size, fps: the film's delivery size and frame rate.
        default_move: the move a plan without one was rendered with (the render's default).
        device_scale_factor: pixels per CSS pixel in the posters.
        still_fields: extra still-record fields per plan (``labelled``, ``subject``, ``title``,
            ``attribution``, ``note``...). ``labelled=True`` needs a ``subject``.
        voice: ``{"voice_id": ..., "model_id": ...}`` recorded on every narration take.
        cut_label: the cut's name in the studio.
        settings: extra cut settings (``size``/``fps`` are always written).
        gaps: things this manifest knows it does not record, in words.
        duration_s, image_size: injected media probes (tests pass fakes).
        label_chars: length of a beat's display snippet.
    """
    root = Path(source_dir).resolve()
    renderable = [p for p in plans if p.view.image_path is not None]
    if not renderable:
        raise ValueError(
            "no plan has a poster image; there is no picture track to write"
        )

    stills: list[dict[str, Any]] = []
    panels: list[dict[str, Any]] = []
    beats: list[dict[str, Any]] = []
    seen: set[str] = set()
    at = 0.0
    for order, plan in enumerate(renderable):
        image = Path(plan.view.image_path)
        key = plan.view.panel_id
        if key not in seen:
            seen.add(key)
            width, height = image_size(image)
            stills.append(
                {
                    "key": key,
                    "path": _relative(image, root),
                    "width": width,
                    "height": height,
                    **dict(still_fields(plan)),
                }
            )
        start, end = at, at + plan.duration_s
        move = plan.move or default_move
        focus = None
        if move.focus is not None:
            fx, fy, fw, fh = normalized_focus(
                move.focus, image_size(image), device_scale_factor=device_scale_factor
            )
            focus = {"x": fx, "y": fy, "w": fw, "h": fh}
        panels.append(
            {
                "still_key": key,
                "start": round(start, 3),
                "end": round(end, 3),
                "move": move.move,
                "zoom": round(move.zoom, 4),
                "focus": focus,
                "seed": order,
                "beat_id": None,
                "order": order,
            }
        )
        if plan.audio_path is not None:
            take_s = min(duration_s(Path(plan.audio_path)), plan.duration_s)
            text = plan.view.caption
            beats.append(
                {
                    "index": len(beats),
                    "kind": "narration",
                    "label": _label(text, label_chars),
                    "text": text,
                    "start": round(start, 3),
                    "end": round(start + take_s, 3),
                    "take": {
                        "path": _relative(plan.audio_path, root),
                        "duration_s": round(take_s, 3),
                        "source": "tts",
                        **dict(voice or {}),
                    },
                }
            )
        at = end

    audio_rel = _relative(audio, root)
    audio_ref = {"path": audio_rel, "duration_s": round(duration_s(Path(audio)), 3)}
    cut = {
        "label": cut_label,
        "artifact": _relative(film, root),
        "audio": audio_ref,
        "duration_s": round(at, 3),
        "width": size[0],
        "height": size[1],
        "fps": fps,
        "profile": "personal",
        "settings": {"size": list(size), "fps": fps, **dict(settings or {})},
        "panels": panels,
        "labels": [],
        "beats": beats,
    }
    return {
        "production": production,
        "title": title,
        "source_dir": ".",
        "rights": dict(rights),
        "episode_audio": audio_ref,
        "stills": stills,
        "cuts": [cut],
        "gaps": list(gaps),
        # the moves above are what the film was framed with, not a source's
        # vocabulary for braidio to reinterpret (needs braidio's `moves` field)
        "moves": "rendered",
    }
