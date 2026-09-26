"""Make the Commentary-screen tour as a real screen recording: a hand clicking through the studio.

``make_studio_tour.py`` photographs each shot and moves a camera over the stills. This script
films the tour instead — the pointer glides, clicks land, lists scroll, the film plays — and cuts
that recording to the same narration. Two cuts:

- ``long`` — :data:`studio_tour.SHOTS` on a 1920×1080 desktop (the same plan and words);
- ``short`` — :data:`studio_tour.SHORT_SHOTS` on a phone, 1080×1920, under a minute.

``python make_screencast_tour.py all --cut long --studio-url … --project-root …`` runs:

1. ``narrate`` — voice every line (cached by content, shared with ``make_studio_tour``'s cache
   when the words are the same) and pace each shot to its line → ``narrated.json``.
2. ``record`` — open the studio in Chrome, start a :class:`CdpScreencastRecorder`, and play the
   paced document in real time (:class:`WallClockPacer`): each shot's gesture
   (:data:`studio_tour.GESTURES`) or command runs at its authored moment, and :class:`StepMarks`
   writes down when it actually began → ``screen.mp4`` + ``recorded.json`` (in-points, overruns)
   and one poster per shot, taken from the recording.
3. ``render`` — braidio's own render (:func:`braidio.video.render_video`) with **footage panels**:
   each shot plays the recording from its in-point, for exactly its narrated span, under the
   assembled narration → ``film.mp4`` + ``recording.wav``.
4. ``manifest`` — :func:`to_production_manifest` with a :class:`FootageTrack` → ``production.json``.
5. ``import`` — ``braidio.importing.import_production`` into ``--project-root``.

The same rule as the still tour: point it only at a studio whose backend is bound to a
**throwaway copy** of the production (shots change a camera move and put it back).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import studio_tour  # noqa: E402
from make_studio_tour import (  # noqa: E402
    BREATH_MS,
    MODEL_ID,
    VOICE_ID,
    VOICE_SETTINGS,
    _load,
    _save,
    _still_fields,
    _tour_commands,
)
from walkthru import DemoDocument, pace_steps_to_narration, realize_narration  # noqa: E402
from walkthru.core.schema import TTS, AssetRef  # noqa: E402

DEFAULT_WORK_ROOT = Path.home() / ".local/share/walkthru/screencast-tour"
#: The still tour's voice cache: its lines, unchanged, are not voiced (or paid for) again.
DEFAULT_TTS_DIR = Path.home() / ".local/share/walkthru/studio-tour/tts"
DEFAULT_STUDIO_URL = "http://localhost:5174"
FPS = 30

#: Per cut: the shots, their gestures, the screen, and the production it becomes.
CUTS: dict[str, dict[str, Any]] = {
    "long": {
        "shots": studio_tour.SHOTS,
        "gestures": studio_tour.GESTURES,
        "doc_id": studio_tour.TOUR_ID,
        "title": studio_tour.TOUR_TITLE,
        "viewport": {"width": 1920, "height": 1080},
        "device_scale_factor": 1.0,
        "mobile": False,
        "cursor": {"shape": "arrow", "size": 26},
        # the same production the still tour was: this recording replaces it
        "production": "commentary-tour",
        "production_title": studio_tour.TOUR_TITLE,
    },
    "short": {
        "shots": studio_tour.SHORT_SHOTS,
        "gestures": studio_tour.SHORT_GESTURES,
        "doc_id": studio_tour.SHORT_ID,
        "title": studio_tour.SHORT_TITLE,
        "viewport": {"width": 432, "height": 768},
        "device_scale_factor": 2.5,  # 432×768 CSS pixels film at 1080×1920
        "mobile": True,
        "cursor": {"shape": "touch", "size": 34},
        "production": "commentary-tour-phone",
        "production_title": "The Commentary screen on a phone (one-minute tour)",
    },
}

#: Pointer glide: this many intermediate moves, which the cursor's own easing smooths.
GLIDE_STEPS = 28
#: A beat between arriving over a control and pressing it, so the eye gets there first.
AIM_MS = 180
#: Typing speed, per character.
TYPE_DELAY_MS = 110
#: Where in its span a shot's poster is taken (after the gesture has had its effect).
POSTER_AT = 0.6
#: A shot that outruns its slot by more than this loses visible action; the record step says so.
OVERRUN_TOLERANCE_MS = 150

RIGHTS = {
    "position": "private",
    "why": (
        "A screen recording of Reelee's own studio, narrated by a synthetic voice. The recording "
        "shows the actually-romantic production, whose pictures are Wikimedia Commons images "
        "under their own licences (credited in that production), and plays a little of its film."
    ),
    "measured": (
        "The footage is a walkthru screen recording against a throwaway copy of "
        "actually-romantic; no third-party audio is used — the recording is the narration only."
    ),
}


def _cut(name: str) -> dict[str, Any]:
    return CUTS[name]


def _document(cut: dict[str, Any]) -> DemoDocument:
    return studio_tour.build_document(cut["shots"], doc_id=cut["doc_id"], title=cut["title"])


# --------------------------------------------------------------------------------------
# 1. narrate
# --------------------------------------------------------------------------------------


async def narrate(work_dir: Path, cut: dict[str, Any], *, tts_dir: Path) -> DemoDocument:
    from walkthru.adapters.synth import MixingSynthesizer, mixing_duration_ms

    synth = MixingSynthesizer(
        voice_id=VOICE_ID, model_id=MODEL_ID, voice_settings=VOICE_SETTINGS, out_dir=tts_dir
    )
    realized = await realize_narration(
        _document(cut), synth=synth, measure_ms=mixing_duration_ms
    )
    paced = pace_steps_to_narration(realized.document, policy="max")
    for segment in paced.tracks.narration:
        segment.tts = TTS(engine="elevenlabs", voice=VOICE_ID)
    for section in paced.sections:
        for step in section.steps:
            step.timing.hold_after_ms = BREATH_MS
    _localize_takes(paced, work_dir / "takes")
    _save(paced, work_dir / "narrated.json")
    return paced


def _localize_takes(doc: DemoDocument, takes_dir: Path) -> None:
    """Copy each line's take out of the shared voice cache into this cut's folder.

    The cache is shared so unchanged lines are never voiced twice; a production, though, keeps
    its files under one folder (the manifest stores paths relative to it)."""
    import shutil

    takes_dir.mkdir(parents=True, exist_ok=True)
    for segment in doc.tracks.narration:
        if segment.audio_ref is None:
            continue
        src = Path(segment.audio_ref.uri)
        dest = takes_dir / src.name
        if src != dest:
            shutil.copy2(src, dest)
            segment.audio_ref = AssetRef(uri=str(dest), mime=segment.audio_ref.mime)


# --------------------------------------------------------------------------------------
# 2. record
# --------------------------------------------------------------------------------------


def _hand(page, locator_of):
    """The gesture vocabulary: what a person's hand does, done visibly."""

    async def target(loc):
        el = locator_of(loc).first
        await el.scroll_into_view_if_needed()
        box = await el.bounding_box()
        if box is None:
            raise RuntimeError(f"not on screen: {loc}")
        return box["x"] + box["width"] / 2, box["y"] + box["height"] / 2

    async def glide(loc):
        x, y = await target(loc)
        await page.mouse.move(x, y, steps=GLIDE_STEPS)
        return x, y

    async def click(loc):
        await glide(loc)
        await page.wait_for_timeout(AIM_MS)
        await page.mouse.down()
        await page.wait_for_timeout(90)
        await page.mouse.up()

    async def settle_scroll(scroller_js: str):
        """Wait until the page (or a dialog) stops moving after a smooth scroll."""
        await page.wait_for_function(
            f"""() => new Promise(r => {{
                const el = {scroller_js}; let last = -1, same = 0;
                const tick = () => {{
                    const now = el.scrollTop;
                    same = now === last ? same + 1 : 0; last = now;
                    if (same >= 4) r(true); else requestAnimationFrame(tick);
                }}; tick();
            }})""",
            timeout=10_000,
        )

    page_scroller = "document.scrollingElement"

    async def scroll_to_y(y_js: str):
        await page.evaluate(f"window.scrollTo({{top: {y_js}, behavior: 'smooth'}})")
        await settle_scroll(page_scroller)

    async def run(op, *, command):
        kind, *args = op
        if kind == "click":
            await click(args[0])
        elif kind == "hover":
            await glide(args[0])
        elif kind == "type":
            await click(args[0])
            await page.keyboard.type(args[1], delay=TYPE_DELAY_MS)
        elif kind == "clear":
            await click(args[0])
            await page.keyboard.press("ControlOrMeta+a")
            await page.keyboard.press("Backspace")
        elif kind == "key":
            await page.keyboard.press(args[0])
        elif kind == "command":
            await command()
        elif kind == "pause":
            await page.wait_for_timeout(int(args[0]))
        elif kind == "scroll_top":
            await scroll_to_y("0")
        elif kind == "scroll_by":
            await scroll_to_y(f"window.scrollY + {int(args[0])}")
        elif kind == "scroll_to":
            text = json.dumps(args[0])
            await scroll_to_y(
                f"""(() => {{ const el = [...document.querySelectorAll('h1,h2,h3,h4,p,span,div')]
                    .find(e => e.childElementCount === 0 && e.textContent.trim() === {text});
                    return el.getBoundingClientRect().top + window.scrollY - 120; }})()"""
            )
        elif kind == "wheel_dialog":
            box = await page.locator("[role=dialog]").last.bounding_box()
            await page.mouse.move(
                box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=GLIDE_STEPS
            )
            scroller = "[...document.querySelectorAll('[role=dialog]')].pop().closest('.st-scrim')"
            await page.evaluate(
                f"dy => {scroller}.scrollBy({{top: dy, behavior: 'smooth'}})", int(args[0])
            )
            await settle_scroll(scroller)
        else:
            raise ValueError(f"unknown gesture op {kind!r}")

    return run


async def record(work_dir: Path, cut: dict[str, Any], *, base_url: str) -> dict[str, Any]:
    """Film the paced tour, and write down where each shot starts in the film."""
    from playwright.async_api import async_playwright

    from walkthru import play, resolve_timeline
    from walkthru.adapters.playwright import (
        CdpScreencastRecorder,
        build_locator,
        install_synthetic_cursor,
        screencast_launch_args,
    )
    from walkthru.core.events import CommandError, StepEnter
    from walkthru.observers import StepMarks, WallClockPacer, in_points, overruns

    doc = _load(work_dir / "narrated.json")
    timeline = resolve_timeline(doc)
    shots = studio_tour.shots_by_id(cut["shots"])
    gestures = cut["gestures"]
    dsf = cut["device_scale_factor"]
    screen = work_dir / "screen.mp4"
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            channel="chrome", args=screencast_launch_args(dsf)
        )
        context = await browser.new_context(
            viewport=cut["viewport"],
            device_scale_factor=dsf,
            is_mobile=cut["mobile"],
            has_touch=cut["mobile"],
        )
        page = await context.new_page()
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await install_synthetic_cursor(page, **cut["cursor"])
        commands = _tour_commands(page, base_url=base_url)
        hand = _hand(page, lambda loc: build_locator(page, loc))

        # the page is open, the film is loaded, and the pointer rests mid-screen before filming
        await commands["tour.open"]({"production": studio_tour.PRODUCTION})
        await page.wait_for_timeout(1500)
        vw, vh = cut["viewport"]["width"], cut["viewport"]["height"]
        await page.mouse.move(vw * 0.62, vh * 0.55)

        current: dict[str, str] = {}
        banned: list[tuple[str, str]] = []

        def track(event):
            if isinstance(event, StepEnter):
                current["step"] = event.step.id
            elif isinstance(event, CommandError):
                raise RuntimeError(f"shot {event.step.id} failed: {event.error}")

        async def executor(command):
            shot = shots[current["step"]]

            async def run_command():
                handler = commands.get(command.id)
                if handler is not None:
                    return await handler(dict(command.params or {}))
                return await commands["_dispatch"](command.id, command.params or {})

            ops = gestures.get(shot.id)
            if ops is None:  # no hand: point where the shot points, then do it
                ops = ((("hover", shot.point),) if shot.point is not None else ()) + (
                    ("command",),
                )
            for op in ops:
                await hand(op, command=run_command)
            # the product never labels a cost "free" (reelee-web#372): audit what is on screen
            words = await page.evaluate("document.body.innerText")
            for phrase in studio_tour.BANNED_PHRASES:
                if re.search(rf"\b{re.escape(phrase)}\b", words, re.IGNORECASE):
                    banned.append((shot.id, phrase))
            return {"ok": True}

        marks = StepMarks()
        recorder = CdpScreencastRecorder(page, save_as=screen, fps=FPS)
        await recorder.start()
        await page.wait_for_timeout(200)  # the first frame, so video time 0 exists
        try:
            await play(doc, executor, observers=[WallClockPacer(), marks, track])
            asset = await recorder.stop()
        finally:
            await browser.close()
        if errors:
            raise RuntimeError("the studio threw during the tour: " + "; ".join(errors))
    for shot_id, phrase in banned:
        print(f"  ! shot {shot_id}: the studio shows {phrase!r} on screen")
    points = in_points(marks.starts, origin=recorder.origin)
    late = overruns(timeline, marks.starts, end=marks.end, tolerance_ms=OVERRUN_TOLERANCE_MS)
    for step_id, ms in late.items():
        print(f"  ! shot {step_id} ran {ms} ms past its slot; its tail is not in the cut")

    posters = work_dir / "posters"
    posters.mkdir(exist_ok=True)
    for step in timeline.steps:
        span_s = (step.end_ms - step.start_ms + step.hold_after_ms) / 1000.0
        poster = posters / f"{step.step_id}.png"
        _frame(screen, points[step.step_id] + POSTER_AT * span_s, poster)
        step.step.poster = AssetRef(uri=str(poster), mime="image/png")
    _save(doc, work_dir / "recorded.json")
    info = {
        "recording": asset.uri,
        "in_points": points,
        "overruns_ms": late,
        "size": _video_size(screen),
        "fps": FPS,
    }
    (work_dir / "recording.json").write_text(json.dumps(info, indent=2))
    return info


def _frame(video: Path, at_s: float, out: Path) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-ss", f"{at_s:.3f}", "-i", str(video),
         "-frames:v", "1", str(out)],
        check=True,
    )  # fmt: skip


def _video_size(video: Path) -> list[int]:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
         "stream=width,height", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()  # fmt: skip
    return [int(v) for v in out.split(",")]


# --------------------------------------------------------------------------------------
# 3. render, 4. manifest, 5. import
# --------------------------------------------------------------------------------------


def _plans(doc: DemoDocument):
    from walkthru import resolve_timeline
    from walkthru.ecosystem.reelee import timeline_to_plans

    return timeline_to_plans(resolve_timeline(doc))


def render(work_dir: Path) -> Path:
    """braidio's render, with every shot a footage panel cut from the recording."""
    from braidio.video import Footage, Panel, render_video
    from mixing import assemble_audio_track

    doc = _load(work_dir / "recorded.json")
    info = json.loads((work_dir / "recording.json").read_text())
    plans = _plans(doc)
    wav = assemble_audio_track(
        [(p.audio_path, p.duration_s) for p in plans], output=work_dir / "recording.wav"
    )
    panels, at = [], 0.0
    for plan in plans:
        panels.append(
            Panel(
                at,
                at + plan.duration_s,
                str(plan.view.image_path),
                footage=Footage(info["recording"], info["in_points"][plan.view.panel_id]),
            )
        )
        at += plan.duration_s
    film = work_dir / "film.mp4"
    render_video(
        panels,
        audio_path=wav,
        out_path=film,
        size=tuple(info["size"]),
        fps=FPS,
        workdir=work_dir / "_render",
    )
    return film


def manifest(work_dir: Path, cut: dict[str, Any]) -> Path:
    from walkthru.ecosystem.reelee import FootageTrack, to_production_manifest

    doc = _load(work_dir / "recorded.json")
    info = json.loads((work_dir / "recording.json").read_text())
    recording = work_dir / "recording.mp3"
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-i", str(work_dir / "recording.wav"),
         "-codec:a", "libmp3lame", "-b:a", "192k", str(recording)],
        check=True,
    )  # fmt: skip
    shots = studio_tour.shots_by_id(cut["shots"])
    data = to_production_manifest(
        _plans(doc),
        production=cut["production"],
        title=cut["production_title"],
        source_dir=work_dir,
        film=work_dir / "film.mp4",
        audio=recording,
        rights=RIGHTS,
        fps=FPS,
        still_fields=lambda plan: {
            **_still_fields_for(plan, shots),
            "attribution": "Frame of a Reelee studio screen recording, captured by walkthru",
        },
        voice={"voice_id": VOICE_ID, "model_id": MODEL_ID},
        cut_label="tour",
        settings={
            "panel_plan": "walkthru Demo Document (examples/reelee_studio_tour), paced to narration",
            "delivery": "walkthru CDP screen recording, cut by braidio footage panels",
        },
        gaps=[
            "Every panel is footage: a stretch of the screen recording, played as a straight "
            "cut. The pictures are frames of that recording, for the studio to show; nothing "
            "moves a camera over them, so their move is hold."
        ],
        footage=FootageTrack(
            path=info["recording"],
            in_points=info["in_points"],
            size=tuple(info["size"]),
            fps=info["fps"],
            note="walkthru CdpScreencastRecorder, paced by WallClockPacer",
        ),
    )
    out = work_dir / "production.json"
    out.write_text(json.dumps(data, indent=2))
    return out


def _still_fields_for(plan, shots) -> dict[str, Any]:
    shot = shots[plan.view.panel_id]
    if plan.view.panel_id in studio_tour.shots_by_id():
        fields = _still_fields(plan)
    else:
        fields = {"labelled": True, "subject": "The Commentary screen, on a phone"}
    return {**fields, "title": f"Commentary screen tour: {shot.id.replace('-', ' ')}"}


def import_(work_dir: Path, project_root: Path, *, dry_run: bool = False):
    from braidio.importing import import_production, load_manifest

    m = load_manifest(work_dir / "production.json")
    return import_production(m, project_root, source_root=work_dir, dry_run=dry_run)


# --------------------------------------------------------------------------------------


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "stage", choices=("narrate", "record", "render", "manifest", "import", "all")
    )
    parser.add_argument("--cut", choices=tuple(CUTS), default="long")
    parser.add_argument("--work-root", type=Path, default=DEFAULT_WORK_ROOT)
    parser.add_argument("--studio-url", default=DEFAULT_STUDIO_URL)
    parser.add_argument("--project-root", type=Path)
    parser.add_argument("--tts-dir", type=Path, default=DEFAULT_TTS_DIR)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)
    cut = _cut(args.cut)
    root = args.work_root.expanduser()
    work = root / args.cut
    work.mkdir(parents=True, exist_ok=True)
    stages = (
        ["narrate", "record", "render", "manifest", "import"]
        if args.stage == "all"
        else [args.stage]
    )
    for stage in stages:
        print(f"[{args.cut}:{stage}]")
        if stage == "narrate":
            asyncio.run(narrate(work, cut, tts_dir=args.tts_dir.expanduser()))
        elif stage == "record":
            info = asyncio.run(record(work, cut, base_url=args.studio_url))
            print(f"  {info['recording']} {info['size']}, overruns: {info['overruns_ms']}")
        elif stage == "render":
            print(render(work))
        elif stage == "manifest":
            print(manifest(work, cut))
        elif stage == "import":
            if args.project_root is None:
                parser.error("import needs --project-root")
            print(import_(work, args.project_root.expanduser(), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
