"""Optional ecosystem adapters — bias toward the ecosystem, depend on it only through ports.

This package holds the (optional) adapters that wire walkthru to Thor's ecosystem: ``acture`` (the
command-dispatch layer that supplies the executor and the capture tap), ``reelee`` (the first
:class:`~walkthru.ports.RenderTarget`, mapping the Demo Document to its Ken Burns ``PanelView``
contract), and ``lacing`` (registering the Demo Document as a body schema). Like
:mod:`walkthru.adapters`, nothing here is imported by the core, and each integration is an optional
extra — so the core runs, tests, and publishes with zero hard dependency on any ecosystem package
(brief §2.1).

Nothing is implemented yet; the reelee ``RenderTarget`` is MVP Stage 5. See ``DECISIONS.md`` §D2/§D3.
"""
