# A tour of reelee-studio's Commentary screen, as a commentary film

A narrated walk through editing a commentary film in [reelee-studio](https://github.com/thorwhalen/reelee-web), using the `actually-romantic` production as the example. It watches a little of the film, reads it as a Storybook, browses its Pictures, opens one moment, changes how the camera moves over it and puts it back, looks at "Use a different picture", and closes.

The tour is rendered as a **real commentary film**: the screenshots are its pictures and the narration is its spoken recording. It is then imported as a commentary *production*, so it opens, and can be edited, on the same screen it tours.

| file | what it is |
| --- | --- |
| `studio_tour.py` | The authoring source: `SHOTS`, one per step (what to do, what to say, where the pointer rests, what the camera closes on), and `build_document()`, which turns them into a walkthru Demo Document. Pure core. |
| `make_studio_tour.py` | The pipeline: `capture → narrate → render → manifest → import`. |

## Re-recording it

Edit `SHOTS` (the words are in `say=`), then run the stages again. Unchanged lines are not re-voiced: clips are cached by their text.

**1. A throwaway copy of the production.** Some shots write to the project (`camera.move` changes a move, and the tour then puts it back). Never run the tour against a live project. Copy it first, from wherever the studio keeps it:

```bash
rsync -a <server>:<studio projects>/actually-romantic/ ~/.local/share/walkthru/commentary-tour/fork/actually-romantic/
```

Copy it again before each capture, so every recording starts from the same state.

**2. A reelee backend bound to the copy, and a studio DEV server proxying to it.** The studio exposes its command registry only in a DEV build opened with `?capture=1`.

```bash
# backend (any free port)
cat > /tmp/tour_server.py <<'EOF'
import os
from pathlib import Path
import muvid.genre, muvid.genre_music_video, braidio.genre
from reelee.server import build_http_app
app = build_http_app(Path(os.environ["TOUR_PROJECT_ROOT"]))
EOF
TOUR_PROJECT_ROOT=~/.local/share/walkthru/commentary-tour/fork/actually-romantic \
  python -m uvicorn --port 8795 --app-dir /tmp tour_server:app

# studio, from a reelee-web checkout
STUDIO_API_TARGET=http://127.0.0.1:8795 npx vite --config vite.studio.config.ts --port 5185
```

**3. Run it.**

```bash
python make_studio_tour.py all --studio-url http://localhost:5185 \
  --project-root ~/.local/share/walkthru/commentary-tour/import/commentary-tour
```

Everything it writes goes to `~/.local/share/walkthru/studio-tour/` (`--work-dir` to change): `shots/`, `tts/`, `captured.json`, `narrated.json`, `film.mp4`, `recording.wav` (and its `.mp3`), `production.json`. None of it belongs in this repository. The screenshots show a production whose pictures carry their own licences.

Import into a **fresh** `--project-root` each time. A re-import updates the project in place and never deletes, so a shot you removed would stay behind as a stale picture, and rewritten pictures make the finished cut read as out of date.

**4. Put the imported project next to the other productions** on the server, and run the studio's `npm run smoke:studio` against a backend bound to it.

## What it needs

`walkthru[playwright,reelee,synth]`, `braidio` with `ProductionManifest.moves`, **Google Chrome** (Playwright's bundled Chromium cannot decode H.264, so the film would show as unplayable in the screenshots), ffmpeg, and `ELEVENLABS_API_KEY`. The voice is ElevenLabs' `eleven_v3` at its most expressive stability setting. The narration is about 3,000 characters.

## Why the film and the studio agree

Each shot's camera is a walkthru `CameraKeyframe`: a focus rect, measured from the page at capture, plus a zoom. `camera_path_builder` frames it with `burns.resolve_move`, the same resolver braidio's own render and the studio's move preview use. `to_production_manifest` writes the same move, zoom and focus into the panel records and declares `moves: "rendered"`, so braidio imports them as recorded instead of rewriting them. Open a moment of the tour in the studio and the move it names is the move the film makes.
