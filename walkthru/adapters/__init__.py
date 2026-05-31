"""Optional, isolated port implementations — the firewall's outer ring.

Each adapter implements one or more :mod:`walkthru.ports` against a concrete tool (Playwright,
OBS/ffmpeg, WhisperX, Piper, driver.js, ...). Adapters depend on ports, **never the reverse**, and
the core never imports anything from here. Each adapter's heavy dependency is an *optional* extra,
so installing walkthru's core pulls in no vendor SDK.

No adapters are implemented yet — the web-first generative path (Playwright player/recorder/
locator + driver.js cues) is MVP Stage 3. See ``PLAN.md`` §3.4 and issue #5.
"""
