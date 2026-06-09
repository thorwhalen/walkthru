"""Concrete :class:`~walkthru.ports.Synthesizer` adapters — hosted text-to-speech.

The :class:`~walkthru.ports.Synthesizer` port (``say(text) -> AssetRef``) gets its first real
implementation here: :class:`MixingSynthesizer`, ElevenLabs TTS via the ``mixing`` package, with the
companion :func:`mixing_duration_ms` duration probe for
:func:`~walkthru.narration.realize.realize_narration`. As an adapter it may import its vendor
(``mixing``) — lazily, behind seam functions — and it is never imported by the core, so the firewall
keeps ``import walkthru`` vendor-free. Install with the ``synth`` extra (``pip install walkthru[synth]``).
"""

from walkthru.adapters.synth.mixing_synth import MixingSynthesizer, mixing_duration_ms

__all__ = ["MixingSynthesizer", "mixing_duration_ms"]
