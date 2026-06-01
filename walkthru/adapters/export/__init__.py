"""Dependency-free export targets — the renderer hand-off and caption sidecars.

These adapters turn a validated Demo Document into the artifacts a renderer or player consumes.
They depend only on the core (schema + :mod:`timeline <walkthru.core.timeline>`), never the reverse,
and pull in no vendor dependency — so they sit behind the ports firewall yet need no optional extra.

* :class:`JsonArtifactTarget` / :func:`to_json` — the frozen JSON projection of the Demo Document,
  the brief's *primary* renderer contract (the renderer owns pixels; we own representation).
* :func:`narration_to_webvtt` — WebVTT captions derived from the narration track, "nearly free"
  from the resolved timeline.
"""

from walkthru.adapters.export.json_target import JsonArtifactTarget, to_json
from walkthru.adapters.export.webvtt import narration_to_webvtt

__all__ = ["JsonArtifactTarget", "to_json", "narration_to_webvtt"]
