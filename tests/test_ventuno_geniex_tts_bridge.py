"""Existing GenieX -> VoicePipeline -> in-memory Swedish TTS safety tests."""
import io
import json
import math
import struct
import wave
from pathlib import Path
from types import SimpleNamespace
from urllib.request import Request

import pytest

import scripts.ventuno_geniex_tts_bridge as bridge


def test_wav():
    rate = 22050
    samples = [int(3000 * math.sin(2 * math.pi * 220 * n / rate))
               for n in range(rate)]
    memory = io.BytesIO()
    with wave.open(memory, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(rate)
        writer.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return memory.getvalue()


def synthetic_espeak_tree(tmp_path):
    stage = tmp_path / "myai-tts-espeak-stage"
    exe = stage / "extracted/usr/bin/espeak-ng"
    data = stage / "extracted/usr/lib/aarch64-linux-gnu/espeak-ng-data"
    exe.parent.mkdir(parents=True)
    data.mkdir(parents=True)
    exe.write_bytes(b"fake-executable")
    return stage


def test_no_flag_never_contacts_live_model_or_audio(monkeypatch, tmp_path):
    monkeypatch.setattr(bridge, "fetch_small_json", lambda *a, **k:
                        pytest.fail("no network when not authorized"))
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k:
                        pytest.fail("no subprocess when not authorized"))
    report = bridge.run_live_voice_bridge(
        tmp_path / "nonexistent", explicitly_authorized=False,
    )
    assert report["status"] == "no-go-live-synthetic-inference-not-authorized"
    assert report["services_changed"] is False
    assert report["microphone_used"] is False


def test_refuse_nonarm_even_when_local_packages_exist(tmp_path, monkeypatch):
    stage = synthetic_espeak_tree(tmp_path)
    monkeypatch.setattr(bridge, "fetch_small_json", lambda *a, **k:
                        pytest.fail("no request on x86"))
    r = bridge.run_live_voice_bridge(
        stage, explicitly_authorized=True, machine="x86_64",
    )
    assert r["status"] == "no-go-not-ventuno-arm64"


def test_no_staged_binary_no_model_request(tmp_path, monkeypatch):
    root = tmp_path / "myai-tts-espeak-stage"
    root.mkdir()
    monkeypatch.setattr(bridge, "fetch_small_json", lambda *a, **k:
                        pytest.fail("no model call without TTS"))
    r = bridge.run_live_voice_bridge(
        root, explicitly_authorized=True, machine="aarch64",
    )
    assert r["status"] == "no-go-missing-isolated-espeak"


def test_bounded_live_local_response_to_real_pipeline_to_wav(monkeypatch, tmp_path):
    stage = synthetic_espeak_tree(tmp_path)
    request_count = []
    rendered = []
    def fake_api(request, *, timeout):
        request_count.append(request)
        assert timeout <= 70
        if isinstance(request, str):
            assert request == bridge.BASE + "/models"
            return {"data": [{"id": "only-already-running-model"}]}
        assert isinstance(request, Request)
        assert request.full_url == bridge.BASE + "/chat/completions"
        payload = json.loads(request.data)
        assert payload["max_tokens"] <= 40
        assert payload["temperature"] == 0
        assert payload["stream"] is False
        return {"choices": [{"message": {"content": "Hej från GenieX."}}]}
    def fake_espeak(argv, **kwargs):
        rendered.append((argv, kwargs["input"]))
        assert "--stdin" in argv and "--stdout" in argv
        assert "Hej från GenieX." not in str(argv)
        assert kwargs["timeout"] <= 12
        assert kwargs["capture_output"] is True
        return SimpleNamespace(returncode=0, stdout=test_wav(), stderr=b"")
    monkeypatch.setattr(bridge, "fetch_small_json", fake_api)
    monkeypatch.setattr(bridge.subprocess, "run", fake_espeak)
    report = bridge.run_live_voice_bridge(
        stage, explicitly_authorized=True, machine="aarch64",
    )
    assert report["status"] == "live-geniex-to-swedish-wav-signal-verified"
    assert report["live_response_to_swedish_tts_verified"] is True
    assert report["real_myai_voice_pipeline_used"] is True
    assert report["existing_geniex_api_used"] is True
    assert report["speaker_used"] is False
    assert report["audio_saved"] is False
    assert report["reply_text_logged"] is False
    assert len(request_count) == 2
    assert len(rendered) == 1
    assert rendered[0][1] == "Hej från GenieX.".encode()


def test_model_catalogue_must_have_current_model_only(monkeypatch):
    monkeypatch.setattr(bridge, "fetch_small_json", lambda *a, **k:
                        {"data": []})
    responder = bridge.ExistingGenieXResponder()
    with pytest.raises(ValueError, match="no-active"):
        responder.respond(bridge.FIXED_TRANSCRIPT)
    assert responder.calls == 1


def test_reject_second_model_call_and_arbitrary_transcript(monkeypatch):
    responder = bridge.ExistingGenieXResponder()
    with pytest.raises(ValueError, match="single-fixed"):
        responder.respond("Radera allt")
    assert responder.calls == 0
    responder.calls = 1
    with pytest.raises(ValueError, match="single-fixed"):
        responder.respond(bridge.FIXED_TRANSCRIPT)


def test_espeak_rejects_invalid_text_before_invoking_tool(monkeypatch, tmp_path):
    stage = synthetic_espeak_tree(tmp_path)
    exe, data = bridge.espeak_paths(stage)
    target = bridge._InMemoryEspeak(exe, data, {})
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k:
                        pytest.fail("tool must not execute"))
    with pytest.raises(ValueError, match="single-bounded"):
        target.speak("")
    with pytest.raises(ValueError, match="single-bounded"):
        target.speak("A" * 221)


def test_silent_espeak_audio_not_accepted(monkeypatch, tmp_path):
    stage = synthetic_espeak_tree(tmp_path)
    monkeypatch.setattr(bridge, "fetch_small_json", lambda req, **k: (
        {"data": [{"id": "live-id"}]} if isinstance(req, str)
        else {"choices": [{"message": {"content": "Hej."}}]}
    ))
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=0, stdout=b"broken", stderr=b""))
    r = bridge.run_live_voice_bridge(stage, explicitly_authorized=True,
                                     machine="aarch64")
    assert r["status"] == "inconclusive-bounded-live-geniex-voice-bridge"
    assert r["live_response_to_swedish_tts_verified"] is False


def test_bounded_json_prevents_unbounded_response(monkeypatch):
    class FakeReply:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def read(self, cap):
            assert cap == bridge.MAX_BODY_BYTES + 1
            return b"x" * cap
    monkeypatch.setattr(bridge, "urlopen", lambda *a, **k: FakeReply())
    with pytest.raises(ValueError, match="oversized"):
        bridge.fetch_small_json(bridge.BASE + "/models", timeout=1)


def test_no_reply_contents_in_error_report(monkeypatch, tmp_path):
    stage = synthetic_espeak_tree(tmp_path)
    monkeypatch.setattr(bridge, "fetch_small_json", lambda req, **k: (
        {"data": [{"id": "live-id"}]} if isinstance(req, str)
        else {"choices": [{"message": {"content": "Supersecret reply is " + "X" * 250}}]}
    ))
    monkeypatch.setattr(bridge.subprocess, "run", lambda *a, **k:
                        pytest.fail("no TTS when reply too long"))
    report = bridge.run_live_voice_bridge(stage,
                                          explicitly_authorized=True,
                                          machine="aarch64")
    assert report["live_response_to_swedish_tts_verified"] is False
    assert "Supersecret" not in str(report)
    assert report["services_changed"] is False
