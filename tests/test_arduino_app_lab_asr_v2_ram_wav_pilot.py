"""Source-only fake Arduino hardware. Never opens a real mic or model."""

import io
from pathlib import Path
import runpy
import sys
from types import ModuleType

import pytest

SOURCE = (Path(__file__).resolve().parents[1] /
          "integrations/arduino_app_lab/asr_v2_official_wav_pilot/python/main.py")
MANIFEST = SOURCE.parents[1] / "app.yaml"


class FakeFrame:
    def __init__(self, samples):
        self.size = samples

    def __getitem__(self, selection):
        assert isinstance(selection, slice)
        assert selection.start is None
        assert selection.step is None
        return FakeFrame(min(self.size, selection.stop))

    def tobytes(self):
        return b"\\x00\\x00" * self.size


def exercise(monkeypatch, capsys, result="Vad heter du?", *,
             start_fails=False, capture_fails=False,
             asr_fails=False, cancel_fails=False,
             bad_format=False, release_fails=False):
    counters = {
        "mic_created": 0, "mic_started": 0, "mic_stopped": 0,
        "mic_captures": 0, "asr_created": 0, "asr_started": 0,
        "asr_transcribed": 0, "asr_cancelled": 0, "wav_bytes": None,
        "order": [],
    }

    class ALSAMicrophone:
        def __init__(self, **kwargs):
            assert kwargs == {
                "device": "plughw:1,0", "sample_rate": 16000,
                "channels": 1, "shared": False, "auto_reconnect": False,
            }
            counters["mic_created"] += 1
            self.sample_rate = 16000
            self.channels = 1
            self.format = "float32" if bad_format else "int16"
            self.opened = False

        def start(self):
            counters["mic_started"] += 1
            if start_fails:
                raise RuntimeError("RAW_MIC_ERROR")
            self.opened = True
            counters["order"].append("mic-open")

        def capture(self):
            assert self.opened
            counters["mic_captures"] += 1
            if capture_fails:
                raise RuntimeError("RAW_PCM_ERROR")
            # Return 8 seconds of synthetic zero-valued PCM in one buffer,
            # so the fake test completes immediately without waiting 8s.
            return FakeFrame(128001)

        def stop(self):
            counters["mic_stopped"] += 1
            self.opened = False
            counters["order"].append("mic-close")
            if release_fails:
                raise RuntimeError("RAW_RELEASE_ERROR")

    class WAVAutomaticSpeechRecognition:
        def __init__(self, *, wav, language, translate):
            assert language == "sv" and translate is False
            assert isinstance(wav, bytes)
            assert counters["mic_stopped"] == 1
            assert counters["order"][-1] == "mic-close"
            counters["asr_created"] += 1
            counters["wav_bytes"] = wav
            import wave
            with wave.open(io.BytesIO(wav), "rb") as file:
                assert file.getframerate() == 16000
                assert file.getnchannels() == 1
                assert file.getsampwidth() == 2
                assert file.getnframes() == 128000

        def transcribe(self):
            counters["asr_transcribed"] += 1
            counters["order"].append("asr-transcribe")
            if asr_fails:
                raise RuntimeError("RAW_TRANSCRIPT")
            return result

        def cancel(self):
            counters["asr_cancelled"] += 1
            if cancel_fails:
                raise RuntimeError("RAW_CANCEL_ERROR")

    class App:
        @staticmethod
        def start_brick(asr):
            assert isinstance(asr, WAVAutomaticSpeechRecognition)
            counters["asr_started"] += 1
            counters["order"].append("asr-start")

        @staticmethod
        def run(*, user_loop):
            for _ in range(2):
                try:
                    user_loop()
                except StopIteration:
                    pass

    modules = {
        "arduino": ModuleType("arduino"),
        "arduino.app_bricks": ModuleType("arduino.app_bricks"),
        "arduino.app_bricks.asr": ModuleType("arduino.app_bricks.asr"),
        "arduino.app_peripherals": ModuleType("arduino.app_peripherals"),
        "arduino.app_peripherals.microphone": ModuleType("arduino.app_peripherals.microphone"),
        "arduino.app_utils": ModuleType("arduino.app_utils"),
    }
    modules["arduino.app_bricks.asr"].WAVAutomaticSpeechRecognition = WAVAutomaticSpeechRecognition
    modules["arduino.app_peripherals.microphone"].ALSAMicrophone = ALSAMicrophone
    modules["arduino.app_utils"].App = App
    for name, module in modules.items():
        monkeypatch.setitem(sys.modules, name, module)

    runpy.run_path(str(SOURCE), run_name="__main__")
    return counters, capsys.readouterr().out


def test_only_official_asr_brick_and_no_legacy():
    yaml = MANIFEST.read_text(encoding="utf-8")
    assert "arduino:asr" in yaml
    assert "arduino:llm" not in yaml
    source = SOURCE.read_text(encoding="utf-8")
    assert "WAVAutomaticSpeechRecognition(" in source
    assert "App.start_brick(asr)" in source
    assert "wave.open(output," in source
    assert 'MIC_DEVICE = "plughw:1,0"' in source
    assert "MAX_CAPTURE_SECONDS = 8" in source
    for forbidden in (
        "arecord", "faster_whisper", "subprocess", "systemctl",
        "open(" + '"recordings', "requests", "Ollama", "GenieX",
        "os.system", "socket", "myai-ventuno.service",
    ):
        assert forbidden not in source


def test_exact_swedish_one_capture_then_offline_asr(monkeypatch, capsys):
    c, out = exercise(monkeypatch, capsys, "Vad heter du?")
    assert c["mic_created"] == 1
    assert c["mic_started"] == c["mic_stopped"] == 1
    assert c["mic_captures"] == 1
    assert c["asr_created"] == c["asr_started"] == 1
    assert c["asr_transcribed"] == c["asr_cancelled"] == 1
    assert c["order"] == [
        "mic-open", "mic-close", "asr-start", "asr-transcribe"
    ]
    assert out.strip().splitlines() == [
        "MYAI_APP_LAB_WAV_V2: capture-started",
        "MYAI_APP_LAB_WAV_V2: reference-recognized",
    ]
    assert c["wav_bytes"][:4] == b"RIFF"
    assert len(c["wav_bytes"]) == 44 + 128000 * 2


@pytest.mark.parametrize("result,expected", [
    ("", "empty-final-only"),
    ("  ", "empty-final-only"),
    ("GODDAG STOCKHOLM", "other-nonempty-final"),
    ("SECRET\\x00", "invalid-final-control"),
    ("x" * 241, "invalid-final-too-long"),
    (None, "invalid-final-type"),
])
def test_result_labels_hide_private_text(monkeypatch, capsys, result, expected):
    c, out = exercise(monkeypatch, capsys, result)
    assert c["mic_stopped"] == 1
    assert c["asr_transcribed"] == 1
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_WAV_V2: " + expected
    assert "SECRET" not in out
    assert "STOCKHOLM" not in out


@pytest.mark.parametrize("kwargs,expected", [
    ({"start_fails": True}, "microphone-open-failed"),
    ({"capture_fails": True}, "capture-failed"),
    ({"bad_format": True}, "format-unsupported"),
    ({"release_fails": True}, "microphone-release-failed"),
])
def test_mic_errors_never_start_asr(monkeypatch, capsys, kwargs, expected):
    c, out = exercise(monkeypatch, capsys, **kwargs)
    assert c["asr_created"] == c["asr_transcribed"] == 0
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_WAV_V2: " + expected
    assert "RAW_" not in out


def test_asr_failure_still_closes_mic_and_masks_raw(monkeypatch, capsys):
    c, out = exercise(monkeypatch, capsys, asr_fails=True)
    assert c["mic_stopped"] == 1
    assert c["asr_started"] == 1
    assert c["asr_transcribed"] == c["asr_cancelled"] == 1
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_WAV_V2: wav-asr-failed"
    assert "RAW_" not in out


def test_cancel_failure_is_not_reported_as_success(monkeypatch, capsys):
    c, out = exercise(monkeypatch, capsys, cancel_fails=True)
    assert c["mic_stopped"] == 1
    assert c["asr_cancelled"] == 1
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_WAV_V2: wav-asr-cancel-failed"
