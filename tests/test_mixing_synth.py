"""Tests for MixingSynthesizer / mixing_duration_ms — injected seams, no mixing/network/ffmpeg."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from walkthru.adapters.synth import MixingSynthesizer, mixing_duration_ms
from walkthru.core.schema import AssetRef


def _fake_synth_fn(calls: list):
    def synth(text, voice_id, path, **kwargs):
        calls.append((text, voice_id, Path(path), kwargs))
        Path(path).write_bytes(b"\x00")
        return Path(path)

    return synth


def test_say_writes_clip_and_returns_assetref(tmp_path):
    calls: list = []
    synth = MixingSynthesizer(voice_id="V1", out_dir=tmp_path, synth_fn=_fake_synth_fn(calls))
    asset = asyncio.run(synth.say("hello"))
    assert isinstance(asset, AssetRef)
    assert asset.mime == "audio/mpeg"
    assert Path(asset.uri).exists()
    assert len(calls) == 1
    assert calls[0][0] == "hello" and calls[0][1] == "V1"
    assert calls[0][3]["model_id"] == "eleven_multilingual_v2"


def test_say_is_idempotent_by_content(tmp_path):
    calls: list = []
    synth = MixingSynthesizer(voice_id="V1", out_dir=tmp_path, synth_fn=_fake_synth_fn(calls))
    a1 = asyncio.run(synth.say("hello"))
    a2 = asyncio.run(synth.say("hello"))
    assert a1.uri == a2.uri
    assert len(calls) == 1  # the second call reused the cached clip


def test_refresh_bypasses_cache_and_propagates_kwarg(tmp_path):
    calls: list = []
    synth = MixingSynthesizer(voice_id="V1", out_dir=tmp_path, refresh=True, synth_fn=_fake_synth_fn(calls))
    asyncio.run(synth.say("hello"))
    asyncio.run(synth.say("hello"))
    assert len(calls) == 2  # refresh=True re-synthesizes even though the clip already exists
    assert calls[0][3].get("refresh") is True  # and forwards refresh into the mixing call


def test_say_distinct_text_distinct_clip(tmp_path):
    calls: list = []
    synth = MixingSynthesizer(voice_id="V1", out_dir=tmp_path, synth_fn=_fake_synth_fn(calls))
    a1 = asyncio.run(synth.say("hello"))
    a2 = asyncio.run(synth.say("world"))
    assert a1.uri != a2.uri
    assert len(calls) == 2


def test_voice_query_resolved_once(tmp_path):
    calls: list = []
    resolves: list[str] = []

    def resolver(query: str) -> str:
        resolves.append(query)
        return "RESOLVED"

    synth = MixingSynthesizer(
        voice_query="narrative_story",
        out_dir=tmp_path,
        synth_fn=_fake_synth_fn(calls),
        voice_resolver=resolver,
    )
    asyncio.run(synth.say("a"))
    asyncio.run(synth.say("b"))
    assert resolves == ["narrative_story"]  # resolved once, then cached
    assert calls[0][1] == "RESOLVED"


def test_requires_exactly_one_voice():
    with pytest.raises(ValueError):
        MixingSynthesizer()
    with pytest.raises(ValueError):
        MixingSynthesizer(voice_id="V", voice_query="q")


def test_mixing_duration_ms_uses_injected_fn():
    asset = AssetRef(uri="/x.mp3", mime="audio/mpeg")
    assert mixing_duration_ms(asset, duration_fn=lambda p: 2.345) == 2345
