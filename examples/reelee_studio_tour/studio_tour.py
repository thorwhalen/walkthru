"""A narrated tour of reelee-studio's Commentary screen, as a walkthru Demo Document.

The tour shows someone how an existing commentary film is edited, using the
``actually-romantic`` production as the example: watch a little of it, read it as a
Storybook, browse its Pictures, open one moment, change how the camera moves over it and
put it back, look at "Use a different picture", and close.

This module is the **authoring source** and is pure core: :data:`SHOTS` is the list a person
edits (what to do, what to say, where the pointer goes, what the camera closes on), and
:func:`build_document` turns it into a :class:`~walkthru.DemoDocument`. Capturing it against a
running studio, voicing it, rendering the film and packaging it as a commentary production is
``make_studio_tour.py``'s job.

Command ids come in two families:

- ``studio.commentary.*`` — the studio's own acture commands (reelee-web ``src/studio/commands``),
  dispatched through ``window.__actureRegistry``. Stable ids, on purpose: this tour replays them.
- ``tour.*`` — page operations the studio has no command for (open the page, seek the film,
  scroll, press a key, click a plain button). ``make_studio_tour.py`` implements them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from walkthru import (
    Command,
    CommandStep,
    DemoDocument,
    Locator,
    NarrationSegment,
    Section,
    Target,
    Timing,
    Tracks,
)
from walkthru.core.schema import (
    Anchor,
    CameraKeyframe,
    CursorCue,
    Meta,
    NarrationAnchor,
)

TOUR_ID = "reelee-commentary-tour"
TOUR_TITLE = "Editing a commentary film — a tour of the Commentary screen"

#: The production the tour walks through, and one moment and pictures inside it.
PRODUCTION = "actually-romantic"
MOMENT = "cf27474c-be9b-5511-953c-e453b28059e6"  # picture 2 of 24, "Taylor Swift"
MOMENT_STILL = (
    "bfe5ac20-8a69-5c38-879e-37124190dd34"  # its picture, used twice in the film
)
OTHER_STILL = "ec496bb2-6b3b-5ec1-81ab-2c6c6aff77b7"  # "The Eras Tour, London"
#: The moment's move as it is in the film, which the tour changes and then restores.
MOMENT_MOVE = "push_in"
TRIED_MOVE = "drift_right"

#: The studio's acture command ids (reelee-web ``src/studio/commands/commentary.ts``) and the
#: page operations ``make_studio_tour.py`` implements. A shot naming anything else is a typo, and
#: a typo'd step is a silent hole in the recorded walk — so :func:`build_document` refuses it.
STUDIO_COMMANDS = frozenset(
    {
        "studio.commentary.tab.show",
        "studio.commentary.moment.open",
        "studio.commentary.picture.open",
        "studio.commentary.library.add",
        "studio.commentary.library.density",
        "studio.commentary.library.narrow",
        "studio.commentary.picker.open",
        "studio.commentary.picker.choose",
        "studio.commentary.picker.use",
        "studio.commentary.camera.move",
        "studio.commentary.camera.closeness",
    }
)
TOUR_COMMANDS = frozenset(
    {
        "tour.open",
        "tour.video.at",
        "tour.scroll",
        "tour.wheel",
        "tour.press",
        "tour.click",
        "tour.noop",
        "tour.wait",
    }
)

#: Nominal screen time per shot; narration-led pacing stretches it to fit what is said.
DEFAULT_SHOT_MS = 4000
#: How close the camera closes on a shot's focus unless the shot says otherwise.
DEFAULT_ZOOM = 1.3


@dataclass(frozen=True)
class Shot:
    """One step of the tour: do something, frame it, say something.

    ``zoom`` above 1 pushes in onto ``focus``; below 1 pulls out from it; exactly 1 holds the
    whole screen still. ``point`` is where the visible pointer rests while the shot is taken.
    """

    id: str
    command: str
    say: str
    params: dict[str, Any] = field(default_factory=dict)
    focus: Optional[Locator] = None
    point: Optional[Locator] = None
    zoom: float = DEFAULT_ZOOM
    section: str = "tour"
    #: Scroll the page before the picture is taken: ``"top"`` (some commands move it).
    scroll: Optional[str] = None
    #: Override the settle time before the picture (a play's first frame wants it short).
    settle_ms: Optional[int] = None


def css(value: str) -> Locator:
    return Locator(strategy="css", value=value)


def text(value: str) -> Locator:
    return Locator(strategy="text", value=value)


def button(name: str) -> Locator:
    return Locator(strategy="role", value="button", name=name)


def heading(name: str) -> Locator:
    return Locator(strategy="role", value="heading", name=name)


TITLE = css(".st-h1")
WATCH = css(".st-watch")
THIS_VERSION = css(".st-watch aside > .st-card:first-child")
TOGETHER_AGAIN = css(".st-watch aside > .st-card:last-child")
STORYBOOK = css("section[aria-label='The film as a page']")
SECOND_PAGE = Locator(strategy="xpath", value="(//article)[2]")
LIBRARY = css(".st-library-shell")
ADD_MENU = css(".st-menu")
IN_ORDER = css("section[aria-label='The pictures, in order']")
#: The dialog on top (the picker opens over a moment's dialog).
DIALOG = Locator(strategy="xpath", value="(//*[@role='dialog'])[last()]")
MOVE_PREVIEW = css("[role=dialog] .st-kb-img")
_DETAILS = ".st-inspector > .st-stack:last-child > section"
HERE_IN_THIS_FILM = css(f"{_DETAILS}:nth-of-type(1)")
THE_PICTURE_ITSELF = css(f"{_DETAILS}:nth-of-type(2)")
THE_WORDS_OVER_IT = css(f"{_DETAILS}:nth-of-type(3)")

#: How long a move preview runs before its second frame is taken.
PLAY_MS = 2400

SHOTS: tuple[Shot, ...] = (
    # --- arriving and watching ------------------------------------------------------------
    Shot(
        "arrive",
        "tour.open",
        "Hi! Welcome to the Commentary screen, where a finished commentary film comes apart "
        "into pieces you can actually change. Today we're poking around Actually Romantic.",
        params={"production": PRODUCTION},
        focus=TITLE,
        zoom=0.75,
        section="watch",
    ),
    Shot(
        "watch-start",
        "tour.video.at",
        "First things first. It's a film, so let's watch a little.",
        params={"seconds": 1.0},
        focus=css("video"),
        point=css("video"),
        section="watch",
    ),
    Shot(
        "watch-middle",
        "tour.video.at",
        "Pictures, over a spoken recording. Each one stays up for a few seconds while the "
        "camera moves slowly across it.",
        params={"seconds": 34.0},
        focus=css("video"),
        zoom=1.2,
        section="watch",
    ),
    Shot(
        "watch-later",
        "tour.video.at",
        "Okay. Lovely! But how is it actually put together?",
        params={"seconds": 97.0, "pause": True},
        focus=css("video"),
        zoom=1.15,
        section="watch",
    ),
    Shot(
        "this-version",
        "tour.noop",
        "The card on the right has the basics: three minutes, twenty-four pictures, and one "
        "card of words on screen.",
        focus=THIS_VERSION,
        point=THIS_VERSION,
        zoom=1.6,
        section="watch",
    ),
    # --- storybook ------------------------------------------------------------------------
    Shot(
        "storybook",
        "studio.commentary.tab.show",
        "Ooh, this one's my favourite. Storybook lays the whole film out on a single page…",
        params={"tab": "storybook"},
        focus=STORYBOOK,
        point=button("Storybook"),
        zoom=1.1,
        section="storybook",
    ),
    Shot(
        "storybook-scroll",
        "tour.scroll",
        "…every picture, in order: when it's up, how the camera moves, the words on screen, "
        "and who to credit. You can even play just that bit.",
        params={"dy": 700},
        focus=SECOND_PAGE,
        zoom=1.35,
        section="storybook",
    ),
    # --- pictures -------------------------------------------------------------------------
    Shot(
        "pictures",
        "studio.commentary.tab.show",
        "Pictures is the library. All seventeen pictures this production owns, whichever "
        "version they end up in.",
        params={"tab": "pictures"},
        focus=LIBRARY,
        point=button("Pictures"),
        zoom=1.1,
        section="pictures",
        scroll="top",
    ),
    Shot(
        "pictures-filters",
        "studio.commentary.library.narrow",
        "You can filter by what a picture shows. Does it say who's in it? Or by whether we "
        "know where it came from.",
        params={"shows": "labelled"},
        focus=css("[role=group][aria-label='What it shows']"),
        point=button("Says who"),
        zoom=1.7,
        section="pictures",
        scroll="top",
    ),
    Shot(
        "pictures-search",
        "studio.commentary.library.narrow",
        "Or just type a name. Say… Charli.",
        params={"shows": "any", "text": "Charli"},
        focus=LIBRARY,
        point=css("input.st-library-search"),
        zoom=1.25,
        section="pictures",
        scroll="top",
    ),
    Shot(
        "pictures-compact",
        "studio.commentary.library.narrow",
        "Clear that, switch to compact…",
        params={"text": ""},
        focus=LIBRARY,
        point=button("Compact"),
        zoom=1.05,
        section="pictures",
        scroll="top",
    ),
    Shot(
        "pictures-compact-view",
        "studio.commentary.library.density",
        "…and you get more pictures at a glance. Just the picture and its label. Tidy!",
        params={"density": "compact"},
        focus=LIBRARY,
        zoom=1.15,
        section="pictures",
        scroll="top",
    ),
    Shot(
        "add-a-picture",
        "tour.click",
        "Need a new one? Add a picture brings one in from your computer, finds one online, "
        "or makes one from a description.",
        params={"name": "Add a picture", "wait_ms": 500},
        focus=ADD_MENU,
        point=button("Add a picture"),
        zoom=1.6,
        section="pictures",
    ),
    Shot(
        "picture-scope",
        "tour.press",
        "Open any picture, and it tells you what it shows, where it came from, and, this is "
        "handy, every place it appears in the film.",
        params={
            "key": "Escape",
            "then": ["studio.commentary.picture.open", {"stillId": MOMENT_STILL}],
        },
        focus=DIALOG,
        zoom=1.15,
        section="pictures",
    ),
    Shot(
        "picture-scope-close",
        "tour.press",
        "Close that, and back to Watch.",
        params={
            "key": "Escape",
            "then": ["studio.commentary.tab.show", {"tab": "watch"}],
        },
        focus=WATCH,
        point=button("Watch"),
        zoom=1.05,
        section="pictures",
    ),
    # --- one moment -----------------------------------------------------------------------
    Shot(
        "in-order",
        "tour.scroll",
        "Scroll down a bit, and here they are: the pictures, in order. All twenty-four, each "
        "with its time and its camera move.",
        params={"to": "The pictures, in order"},
        focus=IN_ORDER,
        zoom=1.3,
        section="moment",
    ),
    Shot(
        "moment-open",
        "studio.commentary.moment.open",
        "Let's click on one, number two, and see what it's made of.",
        params={"panelId": MOMENT},
        focus=DIALOG,
        zoom=1.1,
        section="moment",
    ),
    Shot(
        "moment-parts",
        "tour.noop",
        "A moment is really just a few things: the picture, how the camera moves over it, "
        "and how close it gets.",
        focus=HERE_IN_THIS_FILM,
        point=text("How the camera moves"),
        zoom=1.5,
        section="moment",
    ),
    Shot(
        "moment-play",
        "tour.click",
        "Let's play it.",
        params={"name": "Show the move again"},
        focus=MOVE_PREVIEW,
        point=button("Show the move again"),
        zoom=1.5,
        settle_ms=150,
        section="moment",
    ),
    Shot(
        "moment-play-end",
        "tour.wait",
        "Right now, the camera pushes in. Nice and slow.",
        params={"ms": PLAY_MS},
        focus=MOVE_PREVIEW,
        zoom=1.5,
        settle_ms=0,
        section="moment",
    ),
    Shot(
        "moment-drift",
        "studio.commentary.camera.move",
        "Now let's try something else. How about… drift right?",
        params={"move": TRIED_MOVE},
        focus=HERE_IN_THIS_FILM,
        point=button("Drift right"),
        zoom=1.5,
        section="moment",
    ),
    Shot(
        "moment-play-again",
        "tour.click",
        "Play it again…",
        params={"name": "Show the move again"},
        focus=MOVE_PREVIEW,
        point=button("Show the move again"),
        zoom=1.5,
        settle_ms=150,
        section="moment",
    ),
    Shot(
        "moment-play-again-end",
        "tour.wait",
        "…see that? Instead of moving in, the picture slides sideways. Same picture, "
        "completely different feeling.",
        params={"ms": PLAY_MS},
        focus=MOVE_PREVIEW,
        zoom=1.5,
        settle_ms=0,
        section="moment",
    ),
    Shot(
        "moment-restore",
        "studio.commentary.camera.move",
        "Hmm. I liked it the way it was. Back to push in, exactly where we started.",
        params={"move": MOMENT_MOVE},
        focus=HERE_IN_THIS_FILM,
        point=button("Push in"),
        zoom=1.5,
        section="moment",
    ),
    # --- a different picture --------------------------------------------------------------
    Shot(
        "picker",
        "studio.commentary.picker.open",
        "What if you want a different picture here altogether? Use a different picture "
        "opens the library, right on top of this moment.",
        focus=DIALOG,
        point=button("Use a different picture"),
        zoom=1.1,
        section="picker",
    ),
    Shot(
        "picker-full",
        "studio.commentary.library.density",
        "Switch to full, and you get the titles and the credits too…",
        params={"density": "full"},
        focus=DIALOG,
        point=button("Full"),
        zoom=1.1,
        section="picker",
    ),
    Shot(
        "picker-scroll",
        "tour.wheel",
        "…so there's a bit more to scroll through.",
        params={"dy": 700},
        focus=DIALOG,
        zoom=1.1,
        section="picker",
    ),
    Shot(
        "picker-choose",
        "studio.commentary.picker.choose",
        "Pick one, and before anything changes, it tells you what swapping it in would mean.",
        params={"stillId": OTHER_STILL},
        focus=DIALOG,
        zoom=1.15,
        section="picker",
    ),
    Shot(
        "picker-close",
        "tour.press",
        "But we're only looking today. Close!",
        params={"key": "Escape"},
        focus=DIALOG,
        zoom=1.05,
        section="picker",
    ),
    # --- the rest of the moment -----------------------------------------------------------
    Shot(
        "picture-itself",
        "tour.noop",
        "Below that is the picture itself. Does it say who it shows, and where did it come "
        "from? Change that here, and it changes everywhere the picture is used.",
        focus=THE_PICTURE_ITSELF,
        point=THE_PICTURE_ITSELF,
        zoom=1.5,
        section="moment-more",
    ),
    Shot(
        "words-over-it",
        "tour.noop",
        "And the words over it. Here, that's the title card. Edit them, and only the words "
        "go on again; the moving pictures stay exactly as they are.",
        focus=THE_WORDS_OVER_IT,
        point=THE_WORDS_OVER_IT,
        zoom=1.5,
        section="moment-more",
    ),
    Shot(
        "moment-next",
        "tour.click",
        "Next jumps straight to the following picture. No need to close anything.",
        params={"name": "Next →", "wait_ms": 600},
        focus=DIALOG,
        point=button("Next →"),
        zoom=1.1,
        section="moment-more",
    ),
    Shot(
        "moment-close",
        "tour.press",
        "And when you're done, close it.",
        params={"key": "Escape"},
        focus=IN_ORDER,
        zoom=1.1,
        section="moment-more",
    ),
    # --- putting it together --------------------------------------------------------------
    Shot(
        "together-again",
        "tour.scroll",
        "One last thing. Change something, and this card tells you what making the film "
        "again involves. Here, only words changed, so it's seconds, and free. This one came "
        "in already finished, though, so Reelee can show it, but can't make it again.",
        params={"to": "Putting it together again"},
        focus=TOGETHER_AGAIN,
        point=TOGETHER_AGAIN,
        zoom=1.6,
        section="wrap",
    ),
    Shot(
        "wrap",
        "tour.scroll",
        "And a little secret: this tour is a commentary film too. Open it on this same "
        "screen, and poke at anything you like. Have fun!",
        params={"top": True},
        focus=TITLE,
        zoom=0.75,
        section="wrap",
    ),
)


def _camera_keyframe(shot: Shot) -> CameraKeyframe:
    return CameraKeyframe(
        id=f"cam-{shot.id}", anchor=Anchor(step_id=shot.id), zoom=shot.zoom
    )


def _cursor_cue(shot: Shot) -> Optional[CursorCue]:
    if shot.point is None:
        return None
    return CursorCue(
        id=f"cursor-{shot.id}",
        anchor=Anchor(step_id=shot.id),
        target=Target(primary=shot.point),
    )


def build_document(
    shots: tuple[Shot, ...] = SHOTS, *, shot_ms: int = DEFAULT_SHOT_MS
) -> DemoDocument:
    """The tour as a Demo Document: one step per shot, grouped into sections, with its tracks.

    Narration is anchored to its shot for the shot's nominal time; the camera track holds each
    shot's zoom (its focus rect is filled in at capture, from ``shot.focus``); the pointer's
    resting place is a cursor cue.

    >>> doc = build_document()
    >>> doc.id, len(doc.tracks.narration) == len(SHOTS)
    ('reelee-commentary-tour', True)
    """
    unknown = sorted({shot.command for shot in shots} - STUDIO_COMMANDS - TOUR_COMMANDS)
    if unknown:
        raise ValueError(f"unknown command id(s) in the tour: {', '.join(unknown)}")
    sections: list[Section] = []
    for shot in shots:
        if not sections or sections[-1].id != shot.section:
            sections.append(Section(id=shot.section, steps=[]))
        sections[-1].steps.append(
            CommandStep(
                id=shot.id,
                command=Command(id=shot.command, params=shot.params or None),
                timing=Timing(duration_ms=shot_ms),
            )
        )
    return DemoDocument(
        id=TOUR_ID,
        meta=Meta(title=TOUR_TITLE),
        sections=sections,
        tracks=Tracks(
            cues=[cue for cue in map(_cursor_cue, shots) if cue is not None],
            narration=[
                NarrationSegment(
                    id=f"say-{shot.id}",
                    text=shot.say,
                    anchor=NarrationAnchor(step_id=shot.id, duration_ms=shot_ms),
                )
                for shot in shots
            ],
            camera=[_camera_keyframe(shot) for shot in shots],
        ),
    )


def shots_by_id(shots: tuple[Shot, ...] = SHOTS) -> dict[str, Shot]:
    return {shot.id: shot for shot in shots}


if __name__ == "__main__":
    doc = build_document()
    print(
        f"{doc.id}: {sum(len(s.steps) for s in doc.sections)} shots in {len(doc.sections)} sections"
    )
