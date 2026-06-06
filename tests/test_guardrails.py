"""Executable guardrails against the *inner-platform effect* (issue #6, PLAN.md §7, DECISIONS §D11).

walkthru's dominant failure mode is re-inventing a video editor inside the schema. The schema
models **intent and annotation only**; all compositing, easing, and transitions live in the
**renderer**. These tests turn that prose contract into machine-checked invariants, so the line
stays bright as the schema evolves. Each test that fails is a *deliberate decision point*, not a
bug to paper over — when one trips, justify the change in ``DECISIONS.md`` (and, for a new cue
type, record the rule-of-three) *before* updating the assertion.

The companion guardrail — *no vendor/ecosystem type crosses into ``core``/``ports``* — is enforced
separately by :mod:`tests.test_firewall`; it is intentionally not duplicated here.
"""

from __future__ import annotations

import asyncio
from typing import get_args

from walkthru.core.engine import play
from walkthru.core.events import StepEnter
from walkthru.core.schema import (
    Beat,
    Command,
    CommandStep,
    Cue,
    DemoDocument,
    Section,
    Timing,
    demo_document_json_schema,
)

# --------------------------------------------------------------------------------------
# Cue taxonomy — the rule-of-three gate on a 6th cue type
# --------------------------------------------------------------------------------------

#: The five proven MVP cue variants. A 6th requires a rule-of-three justification recorded in
#: ``DECISIONS.md`` (≥3 distinct cue types sharing ≥80% of handler code) — see issue #6.
EXPECTED_CUE_TYPES = frozenset(
    {"highlight", "spotlight", "hotspot", "callout", "cursor"}
)

#: B-roll lives in the schema only as a *beat slot* (a still + timing), never as PiP/compositing —
#: that is renderer domain. Adding a beat kind is a schema change worth a second look.
EXPECTED_BEAT_KINDS = frozenset({"pause", "textCard", "broll"})


def _literal_value(cue_cls) -> str:
    """The ``type`` discriminator literal of a cue class (e.g. ``HighlightCue`` -> ``"highlight"``)."""
    return get_args(cue_cls.model_fields["type"].annotation)[0]


def test_exactly_the_five_proven_cue_types():
    actual = {_literal_value(cls) for cls in get_args(get_args(Cue)[0])}
    assert actual == set(EXPECTED_CUE_TYPES), (
        "Cue taxonomy changed. A 6th+ cue type needs a rule-of-three justification recorded in "
        "DECISIONS.md (issue #6) before this guardrail is updated; removing one is also a "
        f"deliberate schema decision. expected={sorted(EXPECTED_CUE_TYPES)} actual={sorted(actual)}"
    )


def test_only_the_three_beat_kinds():
    actual = set(get_args(Beat.model_fields["beat_kind"].annotation))
    assert actual == set(EXPECTED_BEAT_KINDS), (
        "Beat kinds changed. B-roll/PiP *compositing* belongs to the renderer, not the schema — a "
        "beat is a slot (still + timing), nothing more. Justify any new kind in DECISIONS.md "
        f"(issue #6). expected={sorted(EXPECTED_BEAT_KINDS)} actual={sorted(actual)}"
    )


# --------------------------------------------------------------------------------------
# Relative time only — no absolute timestamp may enter the SSOT
# --------------------------------------------------------------------------------------

#: Every millisecond-valued field in the schema is a *relative* duration or offset. The SSOT stores
#: no absolute time; global time is derived by ``resolve_timeline`` (DECISIONS §D8).
EXPECTED_RELATIVE_MS_FIELDS = frozenset(
    {"durationMs", "holdAfterMs", "localOffsetMs", "holdMs", "tMs"}
)

#: Field-name fragments that would betray an absolute clock sneaking into the SSOT.
ABSOLUTE_TIME_MARKERS = ("timestamp", "epoch", "absolute", "startat", "atms", "wallclock")


def _all_property_names(json_schema: dict) -> set[str]:
    """Every property name appearing anywhere in the (de-referenced) JSON Schema's ``$defs``."""
    names: set[str] = set()
    for definition in json_schema.get("$defs", {}).values():
        names.update(definition.get("properties", {}).keys())
    names.update(json_schema.get("properties", {}).keys())
    return names


def test_no_absolute_time_in_the_ssot():
    names = _all_property_names(demo_document_json_schema())

    ms_fields = {n for n in names if n.endswith("Ms")}
    assert ms_fields <= set(EXPECTED_RELATIVE_MS_FIELDS), (
        "A new millisecond field appeared. The SSOT stores only relative durations/offsets — never "
        "absolute timestamps (issue #6, DECISIONS §D8). If this field is relative, add it to "
        f"EXPECTED_RELATIVE_MS_FIELDS; if absolute, it does not belong in the SSOT. "
        f"unexpected={sorted(ms_fields - set(EXPECTED_RELATIVE_MS_FIELDS))}"
    )

    absolute = {n for n in names if any(m in n.lower() for m in ABSOLUTE_TIME_MARKERS)}
    assert not absolute, (
        f"Field name(s) suggest an absolute clock in the SSOT: {sorted(absolute)}. Store relative "
        "time only (issue #6); derive global time with resolve_timeline."
    )


# --------------------------------------------------------------------------------------
# Branching seam: reserved, never traversed (the #1 inner-platform-effect trigger)
# --------------------------------------------------------------------------------------


def test_branching_seam_exists_but_is_reserved():
    """``CommandStep.next`` is a type-level seam — it exists, defaults to None, is optional."""
    field = CommandStep.model_fields["next"]
    assert "next" in CommandStep.model_fields
    assert field.is_required() is False and field.default is None


def test_engine_ignores_next_and_plays_linearly():
    """The engine must walk document order and *never* follow ``next``.

    Wiring up branch traversal is the single change most likely to start re-inventing a video
    editor: it is reserved until ≥3 real demos need it (issue #6 / PLAN §7). This pins the engine
    to linear order even when ``next`` points elsewhere; if branching is ever built, change it here
    *and* record the justification first.
    """
    document = DemoDocument(
        id="branch-probe",
        sections=[
            Section(
                id="s1",
                steps=[
                    # step-1.next jumps to step-3; a branch-following engine would skip step-2.
                    CommandStep(
                        id="step-1",
                        command=Command(id="a"),
                        timing=Timing(duration_ms=1),
                        next="step-3",
                    ),
                    CommandStep(
                        id="step-2",
                        command=Command(id="b"),
                        timing=Timing(duration_ms=1),
                    ),
                    CommandStep(
                        id="step-3",
                        command=Command(id="c"),
                        timing=Timing(duration_ms=1),
                    ),
                ],
            )
        ],
    )

    visited: list[str] = []

    def observer(event):
        if isinstance(event, StepEnter):
            visited.append(event.step.id)

    asyncio.run(play(document, lambda command: None, observers=[observer]))
    assert visited == ["step-1", "step-2", "step-3"], (
        "Engine did not play in linear document order — did branch traversal of `next` get built? "
        f"That is reserved until ≥3 demos need it (issue #6). visited={visited}"
    )
