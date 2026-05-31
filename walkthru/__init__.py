"""walkthru — editable, re-renderable demo/tour artifacts from a command sequence.

walkthru owns the *representation* (the Demo Document) and a tiny pure playback/capture
engine, ``play(demoDoc, executor, observers)``. It never renders the final video — it hands a
validated artifact to a renderer (the ``reelee`` ecosystem, Remotion, moviepy/ffmpeg). Owning
representation, not pixels, is the load-bearing boundary of the design.

Two modes share one data model and one engine: *generative* (an author supplies the document;
walkthru plays it while recording) and *capture* (a human drives; walkthru records the video
and the underlying command stream into the same document).

See ``PLAN.md``, ``DECISIONS.md``, and the repository's enhancement issues for the design and
its running development journal. This package currently holds the Python side (schema SSOT +
core + render hand-off); the live capture/play engine ships separately as ``acture-walkthru``.
"""

__version__ = "0.0.1"
