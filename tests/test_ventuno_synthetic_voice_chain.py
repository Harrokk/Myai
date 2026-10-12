"""Fake STT/assistant -> real MyAI VoicePipeline -> synthetic TTS tests.

No audio devices, model imports, GenieX network calls, or production config.
"""
import io
import math
import struct
import wave

import pytest

from scripts.ventuno_synthetic_voice_chain import (
    FIXED_TRANSCRIPT, PHRASE, TEST_TRIGGER,
    _MemoryWavTTS, _SyntheticSTT, run_synthetic_voice_chain,
)


def wav_fixture(*, silent=False) -> bytes:
    hz = 22050
    pcm = [
        0 if silent else int(3000 * math.sin(2 * math.pi * 220 * i / hz))
        for i in range(hz)
    ]
    stream = io.BytesIO()
    with wave.open(stream, "wb") as sink:
        sink.setnchannels(1)
        sink.setsampwidth(2)
        sink.setframerate(hz)
        sink.writeframes(struct.pack("<" + "h" * len(pcm), *pcm))
    return stream.getvalue()


def test_opt_in_gate_never_synthesizes_by_default():
    invoked = []
    report = run_synthetic_voice_chain(
        lambda value: invoked.append(value) or wav_fixture(),
    )
    assert invoked == []
    assert report["status"] == "synthetic-test-not-authorized"
    assert report["microphone_capture_attempted"] is False
    assert report["speaker_playback_attempted"] is False


def test_real_pipeline_forwards_fixed_answer_once_into_wav():
    text_received = []
    def render(value):
        text_received.append(value)
        return wav_fixture()
    report = run_synthetic_voice_chain(render, explicitly_authorized=True)
    assert text_received == [PHRASE]
    assert report["status"] == "synthetic-myai-reply-to-wav-verified"
    assert report["tts_called_exactly_once"] is True
    assert report["real_voice_pipeline_used"] is True
    assert report["tts_signal_verified"] is True
    assert report["sample_rate_hz"] == 22050
    assert report["duration_seconds"] == 1.0
    assert report["actual_stt_model_loaded"] is False
    assert report["live_geniex_called"] is False
    assert report["speaker_playback_attempted"] is False
    assert report["production_services_changed"] is False


def test_non_callable_synthesizer_is_no_go():
    report = run_synthetic_voice_chain(None, explicitly_authorized=True)
    assert report["status"] == "no-go-synthetic-tts-renderer-missing"
    assert report["tts_signal_verified"] is False


def test_silent_wav_is_not_voice_success():
    report = run_synthetic_voice_chain(
        lambda _: wav_fixture(silent=True), explicitly_authorized=True,
    )
    assert report["status"] == "inconclusive-synthetic-voice-chain"
    assert report["tts_signal_verified"] is False


def test_invalid_wav_never_passes():
    report = run_synthetic_voice_chain(
        lambda _: b"not a WAV", explicitly_authorized=True,
    )
    assert report["status"] == "inconclusive-synthetic-voice-chain"
    assert report["tts_signal_verified"] is False


def test_synthetic_stt_requires_exact_trigger():
    stt = _SyntheticSTT()
    with pytest.raises(ValueError, match="synthetic-trigger"):
        stt.transcribe(b"arbitrary-user-audio")
    assert stt.calls == 0
    assert stt.transcribe(TEST_TRIGGER)["text"] == FIXED_TRANSCRIPT


def test_adapter_rejects_arbitrary_text_and_duplicate_speech():
    sent = []
    tts = _MemoryWavTTS(lambda value: sent.append(value) or wav_fixture())
    with pytest.raises(ValueError, match="fixed-synthetic"):
        tts.speak("arbitrary user response")
    assert sent == []
    assert tts.speak(PHRASE) is True
    with pytest.raises(ValueError, match="one-synthetic"):
        tts.speak(PHRASE)
    assert sent == [PHRASE]


def test_renderer_error_refuses_completed_status():
    report = run_synthetic_voice_chain(
        lambda _: (_ for _ in ()).throw(ValueError("fake render failure")),
        explicitly_authorized=True,
    )
    assert report["status"] == "inconclusive-synthetic-voice-chain"
    assert report["live_geniex_called"] is False
