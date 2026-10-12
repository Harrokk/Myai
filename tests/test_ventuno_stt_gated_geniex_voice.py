"""Tests of the STT -> GenieX/TTS boundary without devices or network."""
from pathlib import Path

import pytest

import scripts.ventuno_stt_gated_geniex_voice as module


def verified_stt():
    return {
        "status": "tiny-sv-cpu-word-and-silence-verified",
        "cpu_inference_verified": True,
        "model_files_verified": True,
        "swedish_public_word_attempted": True,
        "swedish_public_word_recognized": True,
        "microphone_used": False,
        "model_installed_in_production": False,
        "geniex_restarted": False,
    }


def fake_live_bridge(**kwargs):
    return {
        "live_response_to_swedish_tts_verified": True,
        "existing_geniex_api_used": True,
        "real_myai_voice_pipeline_used": True,
        "microphone_used": False,
        "speaker_used": False,
        "services_changed": False,
        "audio_saved": False,
        "duration_seconds": 1.25,
        "sample_rate_hz": 22050,
        "rms_fraction_full_scale": 0.042,
    }


def test_no_authorization_prevents_any_api(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "run_live_voice_bridge",
                        lambda *a, **k: pytest.fail("no network allowed"))
    report = module.run_stt_gated_voice_bridge(
        verified_stt(), tmp_path, machine="aarch64"
    )
    assert report["status"] == "not-authorized"
    assert report["local_geniex_requested"] is False
    assert report["microphone_opened"] is False
    assert report["speaker_playback_attempted"] is False


@pytest.mark.parametrize("field,value", [
    ("status", "tiny-sv-cpu-silence-inference-verified"),
    ("cpu_inference_verified", False),
    ("model_files_verified", False),
    ("swedish_public_word_attempted", False),
    ("swedish_public_word_recognized", False),
    ("microphone_used", True),
    ("model_installed_in_production", True),
    ("geniex_restarted", True),
])
def test_malformed_or_unverified_whisper_never_calls_geniex(
    monkeypatch, tmp_path, field, value,
):
    verdict = verified_stt()
    verdict[field] = value
    monkeypatch.setattr(module, "run_live_voice_bridge",
                        lambda *a, **k: pytest.fail("no model call"))
    r = module.run_stt_gated_voice_bridge(
        verdict, tmp_path, authorized=True, machine="aarch64",
    )
    assert r["status"] == "reject-unverified-public-swedish-stt"
    assert r["local_geniex_requested"] is False


@pytest.mark.parametrize("verdict", [None, [], "svenska", {}])
def test_unstructured_whisper_report_never_calls_geniex(
    monkeypatch, tmp_path, verdict,
):
    monkeypatch.setattr(module, "run_live_voice_bridge",
                        lambda *a, **k: pytest.fail("no model call"))
    r = module.run_stt_gated_voice_bridge(
        verdict, tmp_path, authorized=True, machine="aarch64",
    )
    assert r["status"] == "reject-unverified-public-swedish-stt"


def test_wrong_arch_never_calls_local_model(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "run_live_voice_bridge",
                        lambda *a, **k: pytest.fail("no model call"))
    r = module.run_stt_gated_voice_bridge(
        verified_stt(), tmp_path, authorized=True, machine="x86_64",
    )
    assert r["status"] == "reject-non-ventuno-arm64"


def test_low_memory_prevents_geniex(monkeypatch, tmp_path):
    monkeypatch.setattr(module, "mem_available_kib", lambda: 25)
    monkeypatch.setattr(module, "run_live_voice_bridge",
                        lambda *a, **k: pytest.fail("no API under pressure"))
    r = module.run_stt_gated_voice_bridge(
        verified_stt(), tmp_path, authorized=True, machine="aarch64",
    )
    assert r["status"] == "reject-insufficient-ram-after-whisper"
    assert r["local_geniex_requested"] is False


def test_verified_public_sample_can_gate_one_existing_geniex_response(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(module, "mem_available_kib", lambda: 5_000_000)
    calls = []
    def bridge(stage, **kwargs):
        calls.append((stage, kwargs))
        return fake_live_bridge(**kwargs)
    monkeypatch.setattr(module, "run_live_voice_bridge", bridge)
    stage = tmp_path / "myai-tts-espeak-stage"
    r = module.run_stt_gated_voice_bridge(
        verified_stt(), stage, authorized=True, machine="aarch64",
    )
    assert r["status"] == "public-swedish-whisper-gated-geniex-to-wav-verified"
    assert r["whisper_child_finished_before_geniex"] is True
    assert r["real_myai_voice_pipeline_used"] is True
    assert r["geniex_to_wav_verified"] is True
    assert len(calls) == 1
    assert calls[0][0] == stage
    assert calls[0][1] == {"explicitly_authorized": True, "machine": "aarch64"}
    assert r["user_audio_used"] is False
    assert r["microphone_opened"] is False
    assert r["speaker_playback_attempted"] is False
    assert r["stt_transcript_logged"] is False
    assert r["tts_pcm_saved"] is False
    assert "svenska" not in str(r)


@pytest.mark.parametrize("unsafe", [
    {"existing_geniex_api_used": False},
    {"microphone_used": True},
    {"speaker_used": True},
    {"services_changed": True},
    {"audio_saved": True},
    {"live_response_to_swedish_tts_verified": False},
])
def test_unsafe_downstream_results_cannot_be_reported_as_success(
    monkeypatch, tmp_path, unsafe,
):
    monkeypatch.setattr(module, "mem_available_kib", lambda: 5_000_000)
    monkeypatch.setattr(
        module, "run_live_voice_bridge",
        lambda *a, **k: {**fake_live_bridge(), **unsafe},
    )
    r = module.run_stt_gated_voice_bridge(
        verified_stt(), tmp_path, authorized=True, machine="aarch64",
    )
    assert r["status"] == "inconclusive-whisper-gated-geniex-to-wav"
    assert r["geniex_to_wav_verified"] is False


def test_downstream_request_exception_does_not_reveal_transcript(
    monkeypatch, tmp_path,
):
    monkeypatch.setattr(module, "mem_available_kib", lambda: 5_000_000)
    # Real live bridge contains its own bounded API exception handling.
    monkeypatch.setattr(
        module, "run_live_voice_bridge",
        lambda *a, **k: {
            "status": "inconclusive-bounded-live-geniex-voice-bridge",
            "microphone_used": False,
            "speaker_used": False,
            "services_changed": False,
            "audio_saved": False,
        },
    )
    r = module.run_stt_gated_voice_bridge(
        verified_stt(), tmp_path, authorized=True, machine="aarch64",
    )
    assert r["status"] == "inconclusive-whisper-gated-geniex-to-wav"
    assert "stdout" not in str(r)
    assert "stderr" not in str(r)
