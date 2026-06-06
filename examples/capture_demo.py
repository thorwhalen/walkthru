"""Capture mode — record a human's actions into the *same* Demo Document, then replay it.

This is walkthru's second mode. Where :mod:`generative <generative_demo>` mode has an author
supply the document and ``play()`` drive the app, **capture** mode inverts the driver: a human
operates the app, each command is observed *after the fact* as a
:class:`~walkthru.CommandInvocation`, and :func:`walkthru.record` assembles those into a
:class:`~walkthru.DemoDocument` — emitting the *same* lifecycle events, so every observer behaves
identically across the two modes.

The pay-off is that the modes are **inverses over one data model**: a document captured from a
human replays through :func:`walkthru.play` to reproduce exactly the commands that were recorded.
This script proves that round-trip.

In a real capture session the invocation stream comes from an ``ActionRecorder`` adapter tapping
the live command bus (on the TS side, ``acture``'s ``registry.dispatch``); here we simulate it
with a fixed list so the example stays pure-core and dependency-free.

Run it::

    python examples/capture_demo.py
"""

from __future__ import annotations

import asyncio

from walkthru import (
    Command,
    CommandInvocation,
    CommandStep,
    DemoDocument,
    Event,
    play,
    record,
)
from walkthru.adapters.export import to_json


def simulate_human_session() -> list[CommandInvocation]:
    """A fixed stream of already-executed commands, standing in for a live ActionRecorder.

    Each :class:`~walkthru.CommandInvocation` is what the command bus reports *after* the human
    triggered it: the command, its result, and how long it took. A real adapter yields these as
    they happen (``ActionRecorder.record()`` is an async iterator); ``record`` accepts either.
    """
    return [
        CommandInvocation(
            command=Command(id="todo.add", params={"text": "Buy milk"}),
            result={"ok": True, "id": 1},
            duration_ms=1100,
        ),
        CommandInvocation(
            command=Command(id="todo.add", params={"text": "Walk the dog"}),
            result={"ok": True, "id": 2},
            duration_ms=900,
        ),
        CommandInvocation(
            command=Command(id="todo.save"),
            result={"ok": True},
            duration_ms=600,
        ),
    ]


def make_logger(label: str) -> "callable":
    """A logging :data:`~walkthru.Observer`, tagged so we can tell the two phases apart."""

    def log(event: Event) -> None:
        if type(event).__name__ == "AfterCommand":
            print(f"  [{label}] ran {event.command.id}({event.command.params or {}})")

    return log


async def main() -> DemoDocument:
    # --- Phase 1: capture. The human drives; record() assembles the Demo Document. ---
    print("Capturing a human session (capture mode):\n")
    captured = await record(
        simulate_human_session(),
        observers=[make_logger("capture")],
        document_id="todo-captured",
        section_title="Captured session",
    )
    captured_commands = [
        step.command.id
        for step in captured.sections[0].steps
        if isinstance(step, CommandStep)
    ]
    print(
        f"\nCaptured {len(captured_commands)} commands into document '{captured.id}'.\n"
    )

    # --- Phase 2: replay. play() drives the captured document back through an executor. ---
    print("Replaying the captured document (generative mode):\n")
    replayed: list[str] = []

    async def executor(command: Command) -> dict:
        replayed.append(command.id)
        return {"ok": True}

    await play(captured, executor, observers=[make_logger("replay")])

    # --- The point: capture and play are inverses over one data model. ---
    assert replayed == captured_commands, "replay must reproduce the captured commands"
    print(f"\n✅ Round-trip verified: replay reproduced {replayed} exactly.\n")

    print("The captured document (frozen JSON):")
    print(to_json(captured))

    return captured


if __name__ == "__main__":
    asyncio.run(main())
