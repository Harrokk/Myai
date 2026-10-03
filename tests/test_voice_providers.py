import os
from types import SimpleNamespace
import wave

import pytest

from modules.voice import providers


class FakeWord:
    def __init__(self, probability):
        self.probability = probability


class FakeSegment:
    def __init__(
        self,
        text,
        probabilities,
        avg_logprob=-0.1,
    ):
        self.text = text
        self.words = [
            FakeWord(value)
            for value in probabilities
        ]
        self.avg_logprob = avg_logprob


class FakeWhisperModel:
    def __init__(self):
        self.calls = []
        self.last_path = None
        self.wav_info = None

    def transcribe(self, path, **kwargs):
        self.calls.append(kwargs)
        self.last_path = path

        with wave.open(path, "rb") as wav:
            self.wav_info = {
                "channels": wav.getnchannels(),
                "width": wav.getsampwidth(),
                "rate": wav.getframerate(),
                "frames": wav.getnframes(),
            }

        return (
            [
                FakeSegment(
                    "Hej världen",
                    [0.95, 0.50],
                )
            ],
            SimpleNamespace(language="sv"),
        )


def test_faster_whisper_transcribes_pcm16_and_cleans_tempfile():
    model = FakeWhisperModel()

    def factory(name, device, compute_type):
        assert name == "small"
        assert device == "auto"
        assert compute_type == "auto"
        return model

    engine = providers.FasterWhisperSTT(
        model_factory=factory,
        sample_rate=16000,
        uncertain_word_probability=0.60,
    )
    result = engine.transcribe(
        b"\x00\x00" * 160
    )

    assert result["text"] == "Hej världen"
    assert result["confidence"] == pytest.approx(
        0.725,
        abs=0.0001,
    )
    assert result["uncertain_words"] == 1
    assert model.wav_info == {
        "channels": 1,
        "width": 2,
        "rate": 16000,
        "frames": 160,
    }
    assert not os.path.exists(model.last_path)
    assert model.calls[0]["word_timestamps"] is True


def test_faster_whisper_rejects_odd_pcm_bytes():
    engine = providers.FasterWhisperSTT(
        model_factory=lambda *args, **kwargs: FakeWhisperModel(),
    )

    with pytest.raises(ValueError):
        engine.transcribe(b"\x00")


class FakeProcess:
    def __init__(self):
        self.terminated = False
        self.killed = False

    def poll(self):
        return None

    def terminate(self):
        self.terminated = True

    def wait(self, timeout=None):
        return 0

    def kill(self):
        self.killed = True


def test_windows_sapi_starts_encoded_powershell_process():
    seen = {}
    process = FakeProcess()

    def popen(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return process

    engine = providers.WindowsSapiTTS(
        voice_name="Test Voice",
        rate=2,
        volume=80,
        popen_factory=popen,
    )
    started = engine.speak(
        "Hej; Remove-Item C:\\*"
    )

    assert started is True
    script = seen["command"][-1]
    assert "Hej; Remove-Item" not in script
    assert "FromBase64String" in script
    assert "$s.Rate=2" in script
    assert "$s.Volume=80" in script


def test_windows_sapi_stop_terminates_active_process():
    process = FakeProcess()

    engine = providers.WindowsSapiTTS(
        popen_factory=lambda *args, **kwargs: process,
    )
    engine.speak("Hej")

    stopped = engine.stop()

    assert stopped is True
    assert process.terminated is True


def test_empty_provider_configuration_builds_no_engines():
    settings = {
        "voice": {
            "stt_provider": "",
            "tts_provider": "",
        }
    }

    assert providers.build_stt_engines(settings) == []
    assert providers.build_tts_engine(settings) is None


def test_stt_factory_builds_multiple_profiles():
    settings = {
        "voice": {
            "stt_provider": "faster_whisper",
            "stt_model": "small",
            "stt_device": "auto",
            "stt_compute_type": "auto",
            "stt_language": "sv",
            "stt_beam_size": 5,
            "stt_uncertain_word_probability": 0.60,
            "vad_sample_rate": 16000,
            "max_interpretations": 3,
            "stt_profiles": [
                {"beam_size": 1},
                {"beam_size": 5},
            ],
        }
    }

    engines = providers.build_stt_engines(settings)

    assert len(engines) == 2
    assert engines[0].beam_size == 1
    assert engines[1].beam_size == 5


def test_unknown_stt_provider_is_rejected():
    with pytest.raises(ValueError):
        providers.build_stt_engines(
            {
                "voice": {
                    "stt_provider": "unknown",
                }
            }
        )
