"""The first concrete :class:`~walkthru.ports.Synthesizer`: ElevenLabs TTS via the ``mixing`` package.

walkthru ships no built-in TTS — synthesis is a port (``say(text) -> AssetRef``). This adapter is the
hosted-voice tier of PLAN §8 step 6: it speaks each narration line with ElevenLabs through
``mixing.dubbing.synthesize_to_file`` and returns an :class:`~walkthru.core.schema.AssetRef` to the
written clip. As with the reelee render target, the heavy ``mixing`` import is **lazy** (kept inside
seam functions) and every seam is injectable, so importing this module needs no ``mixing``/ffmpeg and
tests run with a fake ``synth_fn``. :func:`mixing_duration_ms` is the companion duration probe for
:func:`~walkthru.narration.realize.realize_narration`.
"""

from __future__ import annotations

import asyncio
import hashlib
from pathlib import Path
from typing import Any, Callable, Mapping, Optional, Union

from walkthru.core.schema import AssetRef

#: Synthesize ``text`` in ``voice_id`` to ``path`` (the ``mixing.dubbing.synthesize_to_file`` shape).
SynthFn = Callable[..., Path]
#: Resolve a human voice *query* ("Brian", "narrative_story") to an ElevenLabs voice id.
VoiceResolver = Callable[[str], str]
#: Measure an audio file's duration, in **seconds**.
DurationFn = Callable[[Union[str, Path]], float]

#: ElevenLabs default model (multilingual, one voice speaks many languages) — matches ``mixing``.
DEFAULT_MODEL_ID = "eleven_multilingual_v2"
#: MP3 is ``mixing``'s default TTS container.
DEFAULT_MIME = "audio/mpeg"


def _default_synth_fn() -> SynthFn:
    from mixing.dubbing import synthesize_to_file

    return synthesize_to_file


def _default_voice_resolver() -> VoiceResolver:
    from mixing.dubbing import find_voice

    def resolve(query: str) -> str:
        voice = find_voice(query)
        if not voice:
            raise ValueError(f"no ElevenLabs voice matches query {query!r}")
        return voice["voice_id"]

    return resolve


def _media_duration_s(path: Union[str, Path]) -> float:
    from mixing.audio import Audio

    return float(Audio(str(path)).full_duration)


def mixing_duration_ms(
    asset: AssetRef, *, duration_fn: Optional[DurationFn] = None
) -> int:
    """Measure a synthesized clip's duration in **milliseconds** (default: via ``mixing``).

    The default :class:`~walkthru.narration.realize.DurationProbe` for
    :func:`~walkthru.narration.realize.realize_narration`. ``duration_fn`` is injected only for
    testing; in production it falls back to ``mixing.audio.Audio(...).full_duration``.
    """
    fn = duration_fn or _media_duration_s
    return int(round(fn(asset.uri) * 1000))


class MixingSynthesizer:
    """A :class:`~walkthru.ports.Synthesizer` backed by ElevenLabs via ``mixing``.

    Synthesized clips are written to ``out_dir`` under a stable hash of ``(voice, model, text)``, so
    re-synthesizing an unchanged line reuses the file rather than re-calling the API (on top of
    ``mixing``'s own content cache). The blocking ``mixing`` call runs in a worker thread, so
    :meth:`say` is a well-behaved coroutine for the async engine.

    Args:
        voice_id: an ElevenLabs voice id to use directly. Exactly one of ``voice_id``/``voice_query``.
        voice_query: a human query ("Brian", "narrative_story") resolved once via
            ``mixing.dubbing.find_voice`` on first use. Exactly one of ``voice_id``/``voice_query``.
        out_dir: directory for the synthesized clips (created on demand).
        model_id, output_format, voice_settings, api_key: forwarded to ``mixing`` TTS
            (``api_key`` defaults to ``$ELEVENLABS_API_KEY`` inside ``mixing``).
        refresh: re-synthesize even if a cached clip exists.
        synth_fn, voice_resolver: injected seams (default: ``mixing``) for testing.

    Raises:
        ValueError: if neither or both of ``voice_id`` / ``voice_query`` are given.
    """

    def __init__(
        self,
        *,
        voice_id: Optional[str] = None,
        voice_query: Optional[str] = None,
        out_dir: Union[str, Path] = ".",
        model_id: str = DEFAULT_MODEL_ID,
        output_format: Optional[str] = None,
        voice_settings: Optional[Mapping[str, Any]] = None,
        api_key: Optional[str] = None,
        refresh: bool = False,
        synth_fn: Optional[SynthFn] = None,
        voice_resolver: Optional[VoiceResolver] = None,
    ):
        if (voice_id is None) == (voice_query is None):
            raise ValueError("provide exactly one of voice_id= or voice_query=")
        self._voice_id = voice_id
        self._voice_query = voice_query
        self._out_dir = Path(out_dir)
        self._model_id = model_id
        self._output_format = output_format
        self._voice_settings = voice_settings
        self._api_key = api_key
        self._refresh = refresh
        self._synth_fn = synth_fn
        self._voice_resolver = voice_resolver
        self._resolved_voice_id: Optional[str] = None

    def _voice(self) -> str:
        if self._resolved_voice_id is None:
            if self._voice_id is not None:
                self._resolved_voice_id = self._voice_id
            else:
                resolver = self._voice_resolver or _default_voice_resolver()
                self._resolved_voice_id = resolver(self._voice_query)  # type: ignore[arg-type]
        return self._resolved_voice_id

    def _clip_path(self, text: str, voice_id: str) -> Path:
        digest = hashlib.sha1(
            f"{voice_id}\0{self._model_id}\0{text}".encode("utf-8")
        ).hexdigest()
        return self._out_dir / f"{digest[:16]}.mp3"

    def _synth_kwargs(self) -> dict[str, Any]:
        kwargs: dict[str, Any] = {"model_id": self._model_id}
        if self._output_format is not None:
            kwargs["output_format"] = self._output_format
        if self._voice_settings is not None:
            kwargs["voice_settings"] = dict(self._voice_settings)
        if self._api_key is not None:
            kwargs["api_key"] = self._api_key
        if self._refresh:
            kwargs["refresh"] = True
        return kwargs

    async def say(self, text: str) -> AssetRef:
        """Synthesize ``text`` to an MP3 clip and return its :class:`AssetRef` (cached by content)."""
        voice_id = self._voice()
        path = self._clip_path(text, voice_id)
        if not (path.exists() and not self._refresh):
            path.parent.mkdir(parents=True, exist_ok=True)
            synth_fn = self._synth_fn or _default_synth_fn()
            await asyncio.to_thread(
                synth_fn, text, voice_id, path, **self._synth_kwargs()
            )
        return AssetRef(uri=str(path), mime=DEFAULT_MIME)
