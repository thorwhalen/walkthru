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
  records describe a film you did not make. The render and this function take the **same**
  :class:`Framing` (default move, aspect, pixel density, easing), so they cannot drift apart,
  and an easing no panel record can carry is refused;
- a narration beat starts where its panel starts, which is where the audio assembler put it.

**A film cut from a screen recording** (a :class:`FootageTrack`) is the same shape: each panel
plays the recording from its step's observed start, as a straight cut, over the same span, and
its poster is the picture the studio shows for it (braidio's footage panels).

The manifest is a plain ``dict`` in braidio's wire shape; nothing here imports braidio, so the
projection is testable anywhere ``reelee`` imports. Validate and import it with
``braidio.importing.load_manifest`` / ``import_production``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional, Union

from walkthru.ecosystem.reelee.render_target import (
    DEFAULT_EASING,
    CameraMove,
    Framing,
    PanelPlan,
    normalized_focus,
)

#: What a still record says about one panel's poster: ``labelled``/``subject``/``title``/...
StillFields = Callable[[PanelPlan], Mapping[str, Any]]

#: A narration beat's timeline snippet is display-only; braidio's own snippets are this long.
DEFAULT_LABEL_CHARS = 48


@dataclass(frozen=True)
class FootageTrack:
    """The screen recording a film was cut from, and where in it each panel starts.

    With one, a panel is **footage**: braidio plays ``path`` from ``in_points[panel_id]`` for the
    panel's span as a straight cut, and the panel's poster is only its picture in the studio. Its
    move is written as ``hold`` at zoom 1, because no camera move is rendered over footage.

    Args:
        path: the recording (an mp4, e.g. from ``CdpScreencastRecorder``).
        in_points: seconds into ``path`` per panel id (``walkthru.observers.in_points``).
        size: the recording's ``(width, height)`` — the film's size.
        fps: the recording's frame rate.
        key: the footage's key in the manifest.
    """

    path: Union[str, Path]
    in_points: Mapping[str, float]
    size: tuple[int, int]
    fps: int
    key: str = "screencast"
    note: Optional[str] = field(default=None)


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


def _video_duration_s(path: Path) -> float:
    """A video's length from its container (a screen recording has no audio to measure)."""
    import subprocess

    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0",
         str(path)],
        capture_output=True, text=True, check=True,
    ).stdout  # fmt: skip
    return float(out.strip())


def _film_size(
    first_image: tuple[int, int], aspect: Optional[float]
) -> tuple[int, int]:
    """The film's frame size, decided exactly as ``burns.ken_burns_film`` decides it."""
    from burns.render import output_size_for

    return output_size_for(*first_image, output_aspect=aspect)


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
    fps: int,
    framing: Framing = Framing(),
    still_fields: StillFields = _default_still_fields,
    voice: Optional[Mapping[str, str]] = None,
    cut_label: str = "v1",
    settings: Optional[Mapping[str, Any]] = None,
    gaps: Sequence[str] = (),
    duration_s: Callable[[Path], float] = _media_duration_s,
    image_size: Callable[[Path], tuple[int, int]] = _image_size,
    film_size: Callable[
        [tuple[int, int], Optional[float]], tuple[int, int]
    ] = _film_size,
    label_chars: int = DEFAULT_LABEL_CHARS,
    footage: Optional[FootageTrack] = None,
    video_duration_s: Callable[[Path], float] = _video_duration_s,
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
        fps: the film's frame rate. Its size is not a parameter: it is worked out the way burns
            worked it out (the first picture at ``framing.aspect``), so it cannot disagree.
        framing: the :class:`Framing` the film was rendered with — pass the one you gave
            :func:`camera_path_builder`. Easing is refused unless it is burns' default, because a
            panel record carries none and braidio's render and the studio's preview use that
            default: the records would describe a differently-paced film.
        still_fields: extra still-record fields per plan (``labelled``, ``subject``, ``title``,
            ``attribution``, ``note``...). ``labelled=True`` needs a ``subject``.
        voice: ``{"voice_id": ..., "model_id": ...}`` recorded on every narration take.
        cut_label: the cut's name in the studio.
        settings: extra cut settings (``size``/``fps`` are always written).
        gaps: things this manifest knows it does not record, in words.
        duration_s, image_size, film_size, video_duration_s: injected media probes (tests pass
            fakes).
        label_chars: length of a beat's display snippet.
        footage: the recording the film was cut from, when it was (see :class:`FootageTrack`);
            every panel then plays it, and ``framing`` is not consulted.
    """
    root = Path(source_dir).resolve()
    renderable = [p for p in plans if p.view.image_path is not None]
    if not renderable:
        raise ValueError(
            "no plan has a poster image; there is no picture track to write"
        )
    if footage is not None:
        missing = [
            p.view.panel_id
            for p in renderable
            if p.view.panel_id not in footage.in_points
        ]
        if missing:
            raise ValueError(f"the footage has no in-point for panels {missing}")
    eased = {
        (p.move or framing.default_move).easing or framing.easing for p in renderable
    }
    if footage is None and eased != {DEFAULT_EASING}:
        raise ValueError(
            f"the film was eased with {sorted(eased)}; a panel record carries no easing, so "
            f"braidio and the studio would replay it as {DEFAULT_EASING!r}. Render with "
            "burns' default easing, or this manifest describes a different film."
        )
    size = (
        tuple(footage.size)
        if footage is not None
        else film_size(image_size(Path(renderable[0].view.image_path)), framing.aspect)
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
        move = plan.move or framing.default_move
        if footage is not None:  # nothing is moved over footage; say so
            move = CameraMove(move="hold", zoom=1.0)
        focus = None
        if move.focus is not None:
            fx, fy, fw, fh = normalized_focus(
                move.focus,
                image_size(image),
                device_scale_factor=framing.device_scale_factor,
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
                **(
                    {"footage": {"key": footage.key, "in_s": footage.in_points[key]}}
                    if footage is not None
                    else {}
                ),
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
    footage_records = []
    if footage is not None:
        length = video_duration_s(Path(footage.path))
        late = {k: v for k, v in footage.in_points.items() if v >= length}
        if late:
            raise ValueError(
                f"in-points at or past the end of the {length:.2f}s recording: {late}"
            )
        footage_records.append(
            {
                "key": footage.key,
                "path": _relative(footage.path, root),
                "width": footage.size[0],
                "height": footage.size[1],
                "fps": footage.fps,
                "duration_s": round(length, 3),
                **({"note": footage.note} if footage.note else {}),
            }
        )
    return {
        "production": production,
        "title": title,
        "source_dir": ".",
        "rights": dict(rights),
        "episode_audio": audio_ref,
        "stills": stills,
        **({"footage": footage_records} if footage_records else {}),
        "cuts": [cut],
        "gaps": list(gaps),
        # the moves above are what the film was framed with, not a source's
        # vocabulary for braidio to reinterpret (needs braidio's `moves` field)
        "moves": "rendered",
    }
