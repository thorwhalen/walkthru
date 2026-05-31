"""The Demo Document schema — the single source of truth (SSOT) for walkthru.

This module authors the Demo Document **once**, in Pydantic v2, as the canonical schema for
both operating modes (generative and capture). JSON is the wire format; the JSON Schema emitted
here (:func:`demo_document_json_schema`) is what the TypeScript side mirrors (codegened Zod) and
what a renderer validates against. See ``DECISIONS.md`` §D1 for why the SSOT is authored
Python-first rather than Zod-first.

Conventions baked into the schema:

* **camelCase on the wire, snake_case in Python.** Every model uses a camelCase alias generator
  with ``populate_by_name=True``, so Python code reads idiomatically while the JSON keys match the
  TypeScript/Zod side.
* **Relative, anchor-based time.** Durations are integer **milliseconds**; there are *no absolute
  timestamps*. Cues, narration, and camera anchor to a ``(stepId, localOffsetMs)`` pair; global
  time is derived by composition. (Report 02 §A.3.)
* **Separate tracks.** Commands live in ``sections[].steps``; cues, narration, and camera live on
  their own :class:`Tracks`, associated to steps **by anchor** — the anchor is the SSOT for that
  association (no denormalized ``cueRefs`` on steps; see ``DECISIONS.md`` §D8).
* **Discriminated unions, not flag soup.** ``Step`` is ``CommandStep | Beat`` (discriminator
  ``kind``); ``Cue`` is the five proven variants (discriminator ``type``).
* **Reserved seams, not built features.** ``CommandStep.next`` is a type-level branching seam with
  no traversal in the engine (Report 02 §Stage 3).
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

Id = str


class _Base(BaseModel):
    """Common config: camelCase wire aliases, populate-by-name, strict extras."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        extra="forbid",
    )


# --------------------------------------------------------------------------------------
# Geometry, locators, and resilient target references
# --------------------------------------------------------------------------------------


class Rect(_Base):
    """An axis-aligned rectangle in CSS pixels (viewport coordinates)."""

    x: float
    y: float
    width: float
    height: float


class Locator(_Base):
    """A single way to find an element. Prefer role/test-id over brittle CSS/XPath."""

    strategy: Literal["role", "testid", "text", "label", "css", "xpath"]
    value: str
    #: Accessible name, used with ``strategy="role"`` to disambiguate.
    name: Optional[str] = None


class ScrollAnchor(_Base):
    """How to re-find a target after the scroll position changes (Report 02 §A.4)."""

    locator: Optional[Locator] = None
    #: Fractional scroll position (0..1) of the scroll container at record time.
    fraction: Optional[float] = None


class Target(_Base):
    """A resilient, prioritized locator: try ``primary``, then ``fallbacks`` in order.

    ``bbox`` is a last-resort geometry captured at record time; ``scrollAnchor`` lets a cue be
    re-anchored after scrolling. Self-healing (re-resolving a drifted target) must be surfaced as
    a human-reviewable suggestion, never a silent rewrite of this SSOT.
    """

    primary: Locator
    fallbacks: list[Locator] = Field(default_factory=list)
    bbox: Optional[Rect] = None
    scroll_anchor: Optional[ScrollAnchor] = None


# --------------------------------------------------------------------------------------
# Timing and anchors (all relative; milliseconds)
# --------------------------------------------------------------------------------------


class Timing(_Base):
    """Local duration of a step, in milliseconds, plus an optional trailing hold."""

    duration_ms: int = Field(ge=0)
    hold_after_ms: Optional[int] = Field(default=None, ge=0)


class Anchor(_Base):
    """A point on a step's local timeline: ``(stepId, localOffsetMs)``."""

    step_id: Id
    local_offset_ms: int = Field(default=0, ge=0)


class NarrationAnchor(_Base):
    """An anchored *span* (a narration segment plays for ``durationMs``)."""

    step_id: Id
    local_offset_ms: int = Field(default=0, ge=0)
    duration_ms: int = Field(ge=0)


# --------------------------------------------------------------------------------------
# Cues — the five proven MVP variants (discriminated by ``type``)
# --------------------------------------------------------------------------------------


class _CueBase(_Base):
    id: Id
    anchor: Anchor
    duration_ms: Optional[int] = Field(default=None, ge=0)
    target: Optional[Target] = None


class HighlightCue(_CueBase):
    """A ring/outline drawn around the target element."""

    type: Literal["highlight"] = "highlight"
    color: Optional[str] = None
    thickness: Optional[int] = None
    padding: Optional[int] = None
    shape: Optional[Literal["rect", "circle"]] = None


class SpotlightCue(_CueBase):
    """A dim surround with a cut-out over the target (focus the viewer)."""

    type: Literal["spotlight"] = "spotlight"
    opacity: Optional[float] = None
    color: Optional[str] = None
    feather: Optional[int] = None


class HotspotCue(_CueBase):
    """A pulsing marker inviting interaction at the target."""

    type: Literal["hotspot"] = "hotspot"
    pulse: Optional[Literal["none", "pulse", "double"]] = None
    size: Optional[int] = None


class CalloutCue(_CueBase):
    """A tooltip/callout with text, optionally with an arrow toward the target."""

    type: Literal["callout"] = "callout"
    text: str
    placement: Optional[Literal["top", "bottom", "left", "right", "auto"]] = None
    arrow: Optional[bool] = None


class CursorCue(_CueBase):
    """A synthetic cursor move, optionally ending in a click.

    ``target`` (inherited) is the destination; ``fromTarget`` is the optional origin.
    """

    type: Literal["cursor"] = "cursor"
    from_target: Optional[Target] = None
    click: Optional[bool] = None
    easing: Optional[str] = None


Cue = Annotated[
    Union[HighlightCue, SpotlightCue, HotspotCue, CalloutCue, CursorCue],
    Field(discriminator="type"),
]


# --------------------------------------------------------------------------------------
# Narration — text is the editable SSOT; media follows the text (Descript model)
# --------------------------------------------------------------------------------------


class AssetRef(_Base):
    """A reference to an external media asset (audio/video/image)."""

    uri: str
    mime: Optional[str] = None


class TTS(_Base):
    """Synthesis parameters; editing ``NarrationSegment.text`` invalidates rendered audio."""

    engine: Optional[str] = None
    voice: Optional[str] = None
    rate: Optional[float] = None
    ssml: Optional[str] = None


class WordTiming(_Base):
    """A single word aligned to a media offset (from STT or TTS marks)."""

    word: str
    t_ms: int = Field(ge=0)


class NarrationSegment(_Base):
    """Timed, editable narration. ``text`` is the source of truth; ``audioRef`` is regenerable."""

    id: Id
    text: str
    anchor: NarrationAnchor
    audio_ref: Optional[AssetRef] = None
    tts: Optional[TTS] = None
    word_timings: Optional[list[WordTiming]] = None


# --------------------------------------------------------------------------------------
# Camera — a first-class track so a pan/zoom can outlast the command that triggered it
# --------------------------------------------------------------------------------------


class CameraKeyframe(_Base):
    """A camera state (focus rect + zoom) anchored to a point in time."""

    id: Id
    anchor: Anchor
    focus: Optional[Rect] = None
    zoom: float = 1.0
    easing: Optional[str] = None
    hold_ms: Optional[int] = Field(default=None, ge=0)


# --------------------------------------------------------------------------------------
# Steps — a discriminated union (CommandStep | Beat)
# --------------------------------------------------------------------------------------


class Command(_Base):
    """A vendor-neutral command: ``{id, params}``.

    Mirrors the ecosystem command shape (acture's ``SequenceStep {commandId, params}``) but stays
    neutral — the ``id <-> commandId`` translation lives in the acture adapter, not here.
    """

    id: str
    params: Optional[dict[str, Any]] = None


class CommandStep(_Base):
    """A step that runs one command."""

    kind: Literal["command"] = "command"
    id: Id
    command: Command
    timing: Timing
    #: RESERVED branching seam — typed but never traversed by the engine (YAGNI / rule of three).
    next: Optional[Id] = None


class Beat(_Base):
    """A non-command step: a pure pause, a title/text card, or a B-roll insert."""

    kind: Literal["beat"] = "beat"
    id: Id
    beat_kind: Literal["pause", "textCard", "broll"]
    timing: Timing
    text: Optional[str] = None


Step = Annotated[Union[CommandStep, Beat], Field(discriminator="kind")]


# --------------------------------------------------------------------------------------
# Document
# --------------------------------------------------------------------------------------


class Tracks(_Base):
    """Parallel annotation tracks, associated to steps by anchor."""

    cues: list[Cue] = Field(default_factory=list)
    narration: list[NarrationSegment] = Field(default_factory=list)
    camera: list[CameraKeyframe] = Field(default_factory=list)


class Meta(_Base):
    """Document metadata."""

    title: Optional[str] = None
    description: Optional[str] = None
    schema_version: str = "0.1.0"


class Section(_Base):
    """An ordered group of steps."""

    id: Id
    title: Optional[str] = None
    steps: list[Step]


class DemoDocument(_Base):
    """The editable, re-renderable demo/tour artifact — walkthru's whole representation."""

    id: Id
    meta: Meta = Field(default_factory=Meta)
    sections: list[Section]
    tracks: Tracks = Field(default_factory=Tracks)


def demo_document_json_schema() -> dict:
    """The published JSON Schema for the Demo Document (camelCase keys).

    This is the cross-language contract: the TypeScript side codegens its Zod types from this, and
    a renderer validates incoming artifacts against it. Regenerate the committed
    ``schema/demo-document.schema.json`` with::

        python -c "import json,walkthru.core.schema as s; \
print(json.dumps(s.demo_document_json_schema(), indent=2))"
    """
    return DemoDocument.model_json_schema(by_alias=True)
