"""The core/adapter firewall: importing the core must pull in no adapter, ecosystem, or vendor SDK.

This is the CI-enforced guarantee from the brief (§6): the dependency graph must make it impossible
for a vendor SDK or ecosystem package to become a hard dependency of the core.
"""

from __future__ import annotations

import importlib
import sys

#: Vendor SDKs / ecosystem packages that must never be imported by the pure core.
FORBIDDEN_PREFIXES = (
    "walkthru.adapters",
    "walkthru.ecosystem",
    "playwright",
    "obsws",
    "whisperx",
    "piper",
    "acture",
    "reelee",
)


def test_core_imports_pull_in_no_adapter_or_vendor():
    # Drop anything already imported so we observe a clean import of the core.
    for name in [m for m in sys.modules if m.startswith(FORBIDDEN_PREFIXES)]:
        del sys.modules[name]

    for module in (
        "walkthru",
        "walkthru.core",
        "walkthru.core.schema",
        "walkthru.core.events",
        "walkthru.core.engine",
        "walkthru.ports",
    ):
        importlib.import_module(module)

    leaked = sorted(m for m in sys.modules if m.startswith(FORBIDDEN_PREFIXES))
    assert not leaked, f"core import pulled in firewalled modules: {leaked}"
