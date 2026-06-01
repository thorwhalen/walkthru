"""The frozen JSON projection — walkthru's primary renderer hand-off.

The boundary the whole design rests on: walkthru owns the *representation* (the Demo Document) and
hands a renderer a validated JSON artifact; the renderer owns the pixels and may ignore anything it
does not understand. :class:`JsonArtifactTarget` is the reference :class:`~walkthru.ports.RenderTarget`
that emits exactly that artifact.
"""

from __future__ import annotations

from pathlib import Path
from typing import Union

from walkthru.core.schema import AssetRef, DemoDocument


def to_json(document: DemoDocument, *, indent: int | None = 2) -> str:
    """The frozen JSON projection (camelCase keys), validated by construction.

    Because ``document`` is a validated :class:`~walkthru.core.schema.DemoDocument`, the emitted
    JSON conforms to the published schema; the TS side / a renderer can consume it directly.
    """
    return document.model_dump_json(by_alias=True, indent=indent)


class JsonArtifactTarget:
    """A :class:`~walkthru.ports.RenderTarget` that writes the Demo Document's JSON projection.

    Args:
        out_dir: directory to write ``<document.id>.json`` into (created on demand).
    """

    def __init__(self, out_dir: Union[str, Path] = "."):
        self._out_dir = Path(out_dir)

    async def export(self, artifact: DemoDocument) -> AssetRef:
        path = self._out_dir / f"{artifact.id}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(to_json(artifact) + "\n", encoding="utf-8")
        return AssetRef(uri=str(path), mime="application/json")
