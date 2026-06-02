"""Optional, isolated port implementations — the firewall's outer ring.

Each adapter implements one or more :mod:`walkthru.ports` against a concrete tool (Playwright,
OBS/ffmpeg, WhisperX, Piper, driver.js, ...). Adapters depend on ports, **never the reverse**, and
the core never imports anything from here. Each adapter's heavy dependency is an *optional* extra,
so installing walkthru's core pulls in no vendor SDK.

Implemented so far: :mod:`walkthru.adapters.export` (the frozen-JSON ``RenderTarget`` and WebVTT
caption export) and :mod:`walkthru.adapters.playwright` (the web-first ``ElementLocator`` +
``Recorder``, PLAN §3.4). The remaining web-first generative-path pieces — the ``acture``
``CommandPlayer`` and the driver.js ``CueRenderer`` — live on the TS side. See ``PLAN.md`` §3.4.
"""
