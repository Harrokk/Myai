"""Safe, deterministic tests for TTS synthesis without speaker playback."""
import io
import math
import struct
import wave
from types import SimpleNamespace

import pytest

import scripts.ventuno_tts_synthesis_probe as tts


def make_wav(sample_rate=22050, seconds=0.6, *, silent=False):
    count = int(sample_rate * seconds)
    samples = [
        0 if silent else int(2400 * math.sin(2 * math.pi * 220 * n / sample_rate))
        for n in range(count)
    ]
    payload = struct.pack("<" + "h" * count, *samples)
    out = io.BytesIO()
    with wave.open(out, "wb") as writer:
        writer.setnchannels(1)
        writer.setsampwidth(2)
        writer.setframerate(sample_rate)
        writer.writeframes(payload)
    return out.getvalue()


def test_default_only_checks_path_without_synthesis(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda name: "/usr/bin/espeak-ng")
    monkeypatch.setattr(tts.subprocess, "run", lambda *a, **kw:
                        pytest.fail("No TTS generation in default mode"))
    result = tts.evaluate_tts()
    assert result["status"] == "tts-cli-present-synthesis-not-attempted"
    assert result["synthetic_synthesis_attempted"] is False
    assert result["physical_speaker_playback_verified"] is False


def test_missing_cli_is_not_synthetic_speech(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda name: None)
    monkeypatch.setattr(tts.subprocess, "run", lambda *a, **kw:
                        pytest.fail("No known CLI; never launch"))
    result = tts.evaluate_tts(synthesize=True)
    assert result["status"] == "tts-cli-not-detected"
    assert result["tts_synthetic_signal_verified"] is False


def test_known_espeak_cli_produces_in_memory_signal(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which",
                        lambda name: "/usr/bin/espeak-ng" if name == "espeak-ng" else None)
    def fake_run(args, **kwargs):
        assert args == ["/usr/bin/espeak-ng", "-v", "sv", "--stdout", tts.PHRASE]
        assert kwargs["timeout"] <= 8
        assert kwargs["capture_output"] is True
        return SimpleNamespace(returncode=0, stdout=make_wav(), stderr=b"")
    monkeypatch.setattr(tts.subprocess, "run", fake_run)
    result = tts.evaluate_tts(synthesize=True)
    assert result["status"] == "swedish-synthetic-tts-wav-verified"
    assert result["sample_rate_hz"] == 22050
    assert result["nonzero_samples"] > 1000
    assert result["tts_synthetic_signal_verified"] is True
    assert result["audio_saved_to_disk"] is False
    assert result["physical_speaker_playback_verified"] is False
    assert result["microphone_opened"] is False
    assert result["production_services_changed"] is False


def test_silent_audio_is_not_speech_success():
    result = tts.validate_wav(make_wav(silent=True))
    assert result["wav_header_valid"] is True
    assert result["signal_verified"] is False


def test_incomplete_or_invalid_wave_is_rejected():
    for raw in (b"", b"RIFFoops", b"private-data", b"x" * 50,
                b"\x00" * (tts.MAX_WAV_BYTES + 1)):
        assert tts.validate_wav(raw)["signal_verified"] is False


def test_exit_failure_is_not_success_and_no_stderr_leaked(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda _: "/bin/espeak")
    monkeypatch.setattr(tts.subprocess, "run", lambda *a, **kw:
                        SimpleNamespace(returncode=2, stdout=b"",
                                        stderr=b"private secret /home/arduino"))
    report = tts.evaluate_tts(synthesize=True)
    assert report["status"] == "tts-cli-nonzero"
    assert "secret" not in str(report)
    assert "arduino" not in str(report)


def test_tts_timeout_fails_closed(monkeypatch):
    monkeypatch.setattr(tts.shutil, "which", lambda _: "/bin/espeak")
    def fail(*a, **k):
        raise __import__("subprocess").TimeoutExpired("tts", 8)
    monkeypatch.setattr(tts.subprocess, "run", fail)
    assert tts.evaluate_tts(synthesize=True)["status"] == "tts-cli-timeout"


def test_only_known_cli_names_are_selected(monkeypatch):
    names = []
    def choose(name):
        names.append(name)
        return "/bin/espeak" if name == "espeak" else None
    monkeypatch.setattr(tts.shutil, "which", choose)
    assert tts.preferred_tts_tool() == ("espeak", "/bin/espeak")
    assert names == ["espeak-ng", "espeak"]
