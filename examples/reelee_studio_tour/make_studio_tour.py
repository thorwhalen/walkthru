"""Make the Commentary-screen tour: capture it, voice it, render it, package it as a production.

``python make_studio_tour.py all`` runs every stage; each stage can also run alone, reading what
the previous one wrote into the work directory (default ``~/.local/share/walkthru/studio-tour``):

1. ``capture`` — play :func:`studio_tour.build_document` against a running studio in Chrome,
   dispatching its acture commands by id, and write one screenshot per shot plus the camera's
   focus rect (the bounding box of ``shot.focus``) into ``captured.json``.
2. ``narrate`` — voice every line with ElevenLabs (``MixingSynthesizer``, cached by content, so a
   re-run of unchanged lines costs nothing) and pace each shot to its line → ``narrated.json``.
3. ``render`` — the reelee Ken Burns render target with :func:`camera_path_builder`, so each
   shot's camera closes on its focus → ``film.mp4`` + ``recording.wav``.
4. ``manifest`` — :func:`to_production_manifest` → ``production.json``, braidio's
   ``ProductionManifest`` for the film just rendered.
5. ``import`` — ``braidio.importing.import_production`` into ``--project-root``.

**What the capture needs, and what it must never touch.** A reelee-studio DEV server (the command
registry is only exposed in a DEV build opened with ``?capture=1``) proxying to a reelee backend
bound to a **throwaway copy** of the production. Shots such as ``camera.move`` write to the
project; the tour puts the move back on screen, but the copy is the real protection. Never point
it at a live project.

Needs: ``walkthru[playwright,reelee,synth]``, Google Chrome (Playwright's bundled Chromium has no
H.264 decoder, so the film would not play in the screenshots), ffmpeg, ``ELEVENLABS_API_KEY`` for
``narrate``, and ``braidio`` for ``import``.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
import sys
from pathlib import Path
from typing import Any, Mapping, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent))

import studio_tour  # noqa: E402
from walkthru import DemoDocument, Target, pace_steps_to_narration, realize_narration  # noqa: E402
from walkthru.core.schema import TTS, AssetRef, CameraKeyframe, Rect  # noqa: E402

DEFAULT_WORK_DIR = Path.home() / ".local/share/walkthru/studio-tour"
DEFAULT_STUDIO_URL = "http://localhost:5174"
VIEWPORT = {"width": 1920, "height": 1080}
FPS = 30

#: The voice: bright and playful, on ElevenLabs' most expressive model.
VOICE_ID = "cgSgspJ2msm6clMCkdW9"  # "Jessica - Playful, Bright, Warm"
MODEL_ID = "eleven_v3"
#: v3 accepts only 0.0 / 0.5 / 1.0 stability; "Creative" (0.0) varies delivery line to line.
VOICE_SETTINGS = {"stability": 0.0, "similarity_boost": 0.75}

#: Settle time after each shot's command before the screenshot, so transitions finish.
SETTLE_MS = 900
#: A small breath after each line, so consecutive lines do not run into each other.
BREATH_MS = 450

PRODUCTION_SLUG = "commentary-tour"


def _framing():
    """How the film frames its shots — handed to BOTH the render and the manifest (see D16)."""
    from walkthru.ecosystem.reelee import Framing

    return Framing(aspect=VIEWPORT["width"] / VIEWPORT["height"])


RIGHTS = {
    "position": "private",
    "why": (
        "Screenshots of Reelee's own studio, narrated by a synthetic voice. The screenshots show "
        "the actually-romantic production, whose pictures are Wikimedia Commons images under "
        "their own licences (credited in that production) and whose film frames carry them."
    ),
    "measured": (
        "Every picture is a screenshot taken by walkthru against a throwaway copy of "
        "actually-romantic; no third-party audio is used — the recording is the narration only."
    ),
}


# --------------------------------------------------------------------------------------
# 1. capture
# --------------------------------------------------------------------------------------


def _tour_commands(page, *, base_url: str) -> dict[str, Any]:
    """The ``tour.*`` vocabulary: page operations the studio has no command for."""

    async def ready():
        # Not "networkidle": in Chrome the film keeps streaming, so the network never idles.
        await page.wait_for_function("() => !!window.__actureRegistry", timeout=30_000)

    async def open_(p):
        url = f"{base_url}/?capture=1#/commentary?production={p['production']}"
        await page.goto(url, wait_until="load")
        await ready()
        await page.wait_for_function(
            "() => { const v = document.querySelector('video'); return v && v.readyState >= 2 }",
            timeout=30_000,
        )

    async def video_at(p):
        await page.evaluate(
            """async ([t, pause]) => {
                const v = document.querySelector('video');
                v.scrollIntoView({block: 'center'});
                v.muted = true;
                await new Promise(r => { v.addEventListener('seeked', r, {once: true}); v.currentTime = t; });
                if (pause) { v.pause(); return; }
                await v.play();
                await new Promise(r => setTimeout(r, 1200));
            }""",
            [float(p["seconds"]), bool(p.get("pause"))],
        )
        await page.evaluate("window.scrollTo({top: 0})")

    async def scroll(p):
        if p.get("top"):
            await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")
        elif p.get("to"):
            await page.get_by_text(p["to"], exact=True).first.evaluate(
                "el => el.scrollIntoView({block: 'start', behavior: 'instant'})"
            )
            await page.evaluate("window.scrollBy({top: -120, behavior: 'instant'})")
        else:
            await page.evaluate(
                f"window.scrollBy({{top: {int(p['dy'])}, behavior: 'instant'}})"
            )

    async def wheel(p):
        """Scroll the dialog on top. It scrolls on its overlay (``.st-scrim``), not itself."""
        box = await page.locator("[role=dialog]").last.bounding_box()
        await page.mouse.move(
            box["x"] + box["width"] / 2, box["y"] + box["height"] / 2, steps=8
        )
        await page.evaluate(
            """dy => [...document.querySelectorAll('[role=dialog]')].pop()
                .closest('.st-scrim').scrollBy({top: dy, behavior: 'instant'})""",
            int(p["dy"]),
        )

    async def press(p):
        await page.keyboard.press(p["key"])
        if p.get("then"):
            command_id, params = p["then"]
            await dispatch(command_id, params)
            await page.evaluate("window.scrollTo({top: 0, behavior: 'instant'})")

    async def click(p):
        await page.get_by_role("button", name=p["name"], exact=True).last.click()
        await page.wait_for_timeout(int(p.get("wait_ms", 0)))

    async def noop(_p):
        return None

    async def wait(p):
        await page.wait_for_timeout(int(p["ms"]))

    async def dispatch(command_id: str, params: Mapping[str, Any]):
        result = await page.evaluate(
            "([id, p]) => window.__actureRegistry.dispatch(id, p)"
            ".then(r => JSON.parse(JSON.stringify(r)))",
            [command_id, dict(params)],
        )
        if not (isinstance(result, dict) and result.get("ok")):
            raise RuntimeError(f"{command_id}({params}) was refused: {result}")
        return result

    return {
        "tour.open": open_,
        "tour.video.at": video_at,
        "tour.scroll": scroll,
        "tour.wheel": wheel,
        "tour.press": press,
        "tour.click": click,
        "tour.noop": noop,
        "tour.wait": wait,
        "_dispatch": dispatch,
    }


async def capture(
    work_dir: Path, *, base_url: str = DEFAULT_STUDIO_URL
) -> DemoDocument:
    """Play the tour in Chrome and write each shot's screenshot and camera focus.

    Driven by walkthru's own :func:`~walkthru.play`: the executor runs each command, and one
    observer puts the pointer on ``shot.point`` before it (``BeforeCommand``) and takes the
    picture after it (``StepExit``). A refused command ends the capture — a tour that skipped a
    step would narrate something that is not on screen.
    """
    from playwright.async_api import async_playwright

    from walkthru import play
    from walkthru.adapters.playwright import (
        PlaywrightElementLocator,
        install_synthetic_cursor,
    )
    from walkthru.core.events import BeforeCommand, CommandError, StepExit

    doc = studio_tour.build_document()
    shots = studio_tour.shots_by_id()
    shots_dir = work_dir / "shots"
    shots_dir.mkdir(parents=True, exist_ok=True)
    focus_rects: dict[str, Any] = {}
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(channel="chrome")
        page = await browser.new_page(viewport=VIEWPORT, device_scale_factor=1)
        errors: list[str] = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        await install_synthetic_cursor(page)
        commands = _tour_commands(page, base_url=base_url)
        locator = PlaywrightElementLocator(page)

        async def executor(command):
            handler = commands.get(command.id)
            if handler is not None:
                return await handler(dict(command.params or {}))
            return await commands["_dispatch"](command.id, command.params or {})

        async def camera_operator(event):
            if isinstance(event, CommandError):
                raise RuntimeError(f"shot {event.step.id} failed: {event.error}")
            if isinstance(event, BeforeCommand):
                point = shots[event.step.id].point
                if point is not None:
                    box = await locator.bounds(Target(primary=point))
                    await page.mouse.move(
                        box.x + box.width / 2, box.y + box.height / 2, steps=12
                    )
            elif isinstance(event, StepExit):
                shot = shots[event.step.id]
                if shot.scroll == "top":
                    await page.evaluate(
                        "window.scrollTo({top: 0, behavior: 'instant'})"
                    )
                await page.wait_for_timeout(
                    SETTLE_MS if shot.settle_ms is None else shot.settle_ms
                )
                focus = (
                    await locator.bounds(Target(primary=shot.focus))
                    if shot.focus is not None
                    else Rect(
                        x=0, y=0, width=VIEWPORT["width"], height=VIEWPORT["height"]
                    )
                )
                if not _on_screen(focus):
                    # found now rather than as a burns error after the narration is paid for
                    raise RuntimeError(
                        f"shot {shot.id}: its focus {shot.focus} is off screen ({focus})"
                    )
                focus_rects[shot.id] = focus
                path = shots_dir / f"{shot.id}.png"
                await page.screenshot(path=str(path))
                event.step.poster = AssetRef(uri=str(path), mime="image/png")
                print(f"  shot {shot.id}")

        try:
            await play(doc, executor, observers=[camera_operator])
        finally:
            await browser.close()
        if errors:
            raise RuntimeError("the studio threw during the tour: " + "; ".join(errors))
    doc.tracks.camera = [
        CameraKeyframe(
            **{**kf.model_dump(), "focus": focus_rects.get(kf.anchor.step_id)}
        )
        for kf in doc.tracks.camera
    ]
    _save(doc, work_dir / "captured.json")
    return doc


def _on_screen(rect: Rect, *, min_px: float = 8.0) -> bool:
    """Does ``rect`` show at least a sliver of itself in the viewport?"""
    visible_w = min(rect.x + rect.width, VIEWPORT["width"]) - max(rect.x, 0)
    visible_h = min(rect.y + rect.height, VIEWPORT["height"]) - max(rect.y, 0)
    return visible_w >= min_px and visible_h >= min_px


# --------------------------------------------------------------------------------------
# 2. narrate
# --------------------------------------------------------------------------------------


async def narrate(work_dir: Path) -> DemoDocument:
    """Voice every line (cached by content) and pace each shot to what is said over it."""
    from walkthru.adapters.synth import MixingSynthesizer, mixing_duration_ms

    doc = _load(work_dir / "captured.json")
    synth = MixingSynthesizer(
        voice_id=VOICE_ID,
        model_id=MODEL_ID,
        voice_settings=VOICE_SETTINGS,
        out_dir=work_dir / "tts",
    )
    realized = await realize_narration(doc, synth=synth, measure_ms=mixing_duration_ms)
    paced = pace_steps_to_narration(realized.document, policy="max")
    for segment in paced.tracks.narration:
        segment.tts = TTS(engine="elevenlabs", voice=VOICE_ID)
    for section in paced.sections:
        for step in section.steps:
            step.timing.hold_after_ms = BREATH_MS
    _save(paced, work_dir / "narrated.json")
    return paced


# --------------------------------------------------------------------------------------
# 3. render, 4. manifest, 5. import
# --------------------------------------------------------------------------------------


def _plans(doc: DemoDocument):
    from walkthru import resolve_timeline
    from walkthru.ecosystem.reelee import timeline_to_plans

    return timeline_to_plans(resolve_timeline(doc))


def render(work_dir: Path) -> Path:
    from walkthru.ecosystem.reelee import camera_path_builder, render_plans

    doc = _load(work_dir / "narrated.json")
    film = work_dir / "film.mp4"
    render_plans(
        _plans(doc),
        film,
        fps=FPS,
        path_builder=camera_path_builder(_framing()),
        audio_out=work_dir / "recording.wav",
    )
    return film


#: What each section's screenshots show, as the picture's label in the studio.
SECTION_SUBJECTS = {
    "watch": "The Commentary screen, Watch tab",
    "storybook": "The Commentary screen, Storybook tab",
    "pictures": "The Commentary screen, Pictures tab",
    "moment": "One moment of the film, open",
    "picker": "Pick another picture",
    "moment-more": "One moment of the film, open",
    "wrap": "The Commentary screen",
}


def _still_fields(plan) -> dict[str, Any]:
    shot = studio_tour.shots_by_id()[plan.view.panel_id]
    return {
        "labelled": True,
        "subject": SECTION_SUBJECTS.get(shot.section, "The Commentary screen"),
        "title": f"Commentary screen tour: {shot.id.replace('-', ' ')}",
        "attribution": "Screenshot of Reelee studio, captured by walkthru",
        "note": "Shows the actually-romantic production; its pictures are credited there.",
    }


def manifest(work_dir: Path) -> Path:
    from walkthru.ecosystem.reelee import to_production_manifest

    doc = _load(work_dir / "narrated.json")
    # braidio serves an episode as audio/mpeg; the render's recording is PCM WAV. Same audio.
    recording = work_dir / "recording.mp3"
    subprocess.run(
        [
            "ffmpeg",
            "-v",
            "error",
            "-y",
            "-i",
            str(work_dir / "recording.wav"),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "192k",
            str(recording),
        ],
        check=True,
    )
    data = to_production_manifest(
        _plans(doc),
        production=PRODUCTION_SLUG,
        title=studio_tour.TOUR_TITLE,
        source_dir=work_dir,
        film=work_dir / "film.mp4",
        audio=recording,
        rights=RIGHTS,
        fps=FPS,
        framing=_framing(),
        still_fields=_still_fields,
        voice={"voice_id": VOICE_ID, "model_id": MODEL_ID},
        cut_label="tour",
        settings={
            "panel_plan": "walkthru Demo Document (examples/reelee_studio_tour), paced to narration",
            "delivery": "walkthru reelee render target, camera_path_builder (burns.resolve_move)",
        },
        gaps=[
            "The moves are the walkthru camera track's: push in onto each shot's focus, pull out "
            "on the first and last shot. Rendered by burns.resolve_move, the resolver braidio's "
            "own render uses, so a re-render from these panels frames the same."
        ],
    )
    out = work_dir / "production.json"
    out.write_text(json.dumps(data, indent=2))
    return out


def import_(work_dir: Path, project_root: Path, *, dry_run: bool = False):
    from braidio.importing import import_production, load_manifest

    m = load_manifest(work_dir / "production.json")
    return import_production(m, project_root, source_root=work_dir, dry_run=dry_run)


# --------------------------------------------------------------------------------------


def _save(doc: DemoDocument, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(doc.model_dump_json(by_alias=True, indent=2))


def _load(path: Path) -> DemoDocument:
    return DemoDocument.model_validate_json(path.read_text())


def main(argv: Optional[list[str]] = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "stage", choices=("capture", "narrate", "render", "manifest", "import", "all")
    )
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_DIR)
    parser.add_argument("--studio-url", default=DEFAULT_STUDIO_URL)
    parser.add_argument(
        "--project-root", type=Path, help="Where `import` writes the project."
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="`import`: validate only."
    )
    args = parser.parse_args(argv)
    work = args.work_dir.expanduser()
    stages = (
        ["capture", "narrate", "render", "manifest", "import"]
        if args.stage == "all"
        else [args.stage]
    )
    for stage in stages:
        print(f"[{stage}]")
        if stage == "capture":
            asyncio.run(capture(work, base_url=args.studio_url))
        elif stage == "narrate":
            asyncio.run(narrate(work))
        elif stage == "render":
            print(render(work))
        elif stage == "manifest":
            print(manifest(work))
        elif stage == "import":
            if args.project_root is None:
                parser.error("import needs --project-root")
            print(import_(work, args.project_root.expanduser(), dry_run=args.dry_run))


if __name__ == "__main__":
    main()
