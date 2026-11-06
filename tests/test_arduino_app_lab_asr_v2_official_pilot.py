"""Host-only fake Arduino API tests: NO audio device or real ASR service."""
from dataclasses import dataclass
from pathlib import Path
import runpy
import sys
from types import ModuleType

import pytest

APP = (Path(__file__).resolve().parents[1] /
       "integrations/arduino_app_lab/asr_v2_official_pilot")
SOURCE = APP / "python/main.py"


@dataclass(frozen=True)
class Event:
    type: str
    data: object


class FakeStream:
    def __init__(self, events, *, exit_fails=False):
        self.events = events
        self.entered = 0
        self.exited = 0
        self.exit_fails = exit_fails

    def __enter__(self):
        self.entered += 1
        return iter(self.events)

    def __exit__(self, typ, exc, tb):
        self.exited += 1
        if self.exit_fails:
            raise RuntimeError("PRIVATE_FINAL_TEXT")
        return False


def execute(monkeypatch, capsys, events=(), *, asr_fails=False,
            stream_exit_fails=False, cancel_fails=False,
            mic_start_fails=False, mic_stop_fails=False):
    counts = {
        "created": 0, "sessions": [], "cancelled": 0, "calls": 0,
        "mic_created": 0, "mic_started": 0, "mic_stopped": 0,
        "order": [],
    }
    top = ModuleType("arduino")
    bricks = ModuleType("arduino.app_bricks")
    asr_module = ModuleType("arduino.app_bricks.asr")
    peripherals = ModuleType("arduino.app_peripherals")
    microphone = ModuleType("arduino.app_peripherals.microphone")
    utils = ModuleType("arduino.app_utils")
    streams = []

    class ALSAMicrophone:
        def __init__(self, *, device, shared, auto_reconnect):
            assert device == "plughw:1,0"
            assert shared is False and auto_reconnect is False
            counts["mic_created"] += 1
            counts["order"].append("construct-mic")
            self.running = False

        def start(self):
            counts["mic_started"] += 1
            counts["order"].append("mic-start")
            if mic_start_fails:
                raise RuntimeError("PRIVATE_MIC_OPEN_ERROR")
            self.running = True

        def stop(self):
            counts["mic_stopped"] += 1
            counts["order"].append("mic-stop")
            self.running = False
            if mic_stop_fails:
                raise RuntimeError("PRIVATE_MIC_RELEASE_ERROR")

    class AutomaticSpeechRecognition:
        def __init__(self, *, mic, language, translate):
            assert isinstance(mic, ALSAMicrophone)
            assert language == "sv" and translate is False
            counts["created"] += 1
            counts["order"].append("construct-asr")
            self.mic = mic

        def transcribe_sentence_stream(self, *, timeout):
            assert self.mic.running
            counts["sessions"].append(timeout)
            counts["order"].append("asr-session")
            if asr_fails:
                raise RuntimeError("PRIVATE_RAW_TRANSCRIPT")
            s = FakeStream(events, exit_fails=stream_exit_fails)
            streams.append(s)
            return s

        def cancel(self):
            counts["cancelled"] += 1
            counts["order"].append("asr-cancel")
            if cancel_fails:
                raise RuntimeError("PRIVATE_DEVICE_DETAIL")

    class App:
        @staticmethod
        def run(*, user_loop):
            for _ in range(3):
                counts["calls"] += 1
                try:
                    user_loop()
                except StopIteration:
                    pass

    asr_module.AutomaticSpeechRecognition = AutomaticSpeechRecognition
    microphone.ALSAMicrophone = ALSAMicrophone
    utils.App = App
    for name, obj in {
        "arduino": top, "arduino.app_bricks": bricks,
        "arduino.app_bricks.asr": asr_module,
        "arduino.app_peripherals": peripherals,
        "arduino.app_peripherals.microphone": microphone,
        "arduino.app_utils": utils,
    }.items():
        monkeypatch.setitem(sys.modules, name, obj)
    runpy.run_path(str(SOURCE), run_name="__main__")
    return counts, streams, capsys.readouterr().out


def test_manifest_official_asr_and_explicit_usb_mic_no_legacy():
    manifest = (APP / "app.yaml").read_text(encoding="utf-8")
    assert "bricks:\n  - arduino:asr" in manifest
    assert "arduino:llm" not in manifest
    source = SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "ventuno_usb", "faster_whisper", "arecord", "aplay",
        "systemctl", "sudo", "GenieXClient", "OllamaClient",
        "requests", "whisper.tiny", "subprocess",
    ):
        assert forbidden not in source
    assert 'MIC_DEVICE = "plughw:1,0"' in source
    assert "ALSAMicrophone(" in source
    assert "shared=False, auto_reconnect=False" in source
    assert "AutomaticSpeechRecognition(mic=mic, language=" in source
    assert "transcribe_sentence_stream(timeout=MAX_SENTENCE_SECONDS)" in source
    assert "mic.start()" in source and "mic.stop()" in source
    assert "App.run(user_loop=run_one)" in source


def test_exact_phrase_uses_one_explicit_device_and_releases(monkeypatch, capsys):
    c, s, output = execute(
        monkeypatch, capsys,
        [Event("partial_text", "hemligt"),
         Event("full_text", "Vad heter du?"),
         Event("full_text", "andra meningen")],
    )
    assert c["mic_created"] == 1 and c["created"] == 1
    assert c["mic_started"] == c["mic_stopped"] == 1
    assert c["sessions"] == [8]
    assert c["cancelled"] == 1
    assert s[0].entered == s[0].exited == 1
    assert c["order"] == [
        "construct-mic", "construct-asr", "mic-start",
        "asr-session", "asr-cancel", "mic-stop",
    ]
    assert output.strip().splitlines() == [
        "MYAI_APP_LAB_ASR_V2: microphone-opened",
        "MYAI_APP_LAB_ASR_V2: reference-recognized",
    ]
    assert "hemligt" not in output and "andra meningen" not in output


def test_other_swedish_sentence_not_logged(monkeypatch, capsys):
    c, _, out = execute(
        monkeypatch, capsys,
        [Event("full_text", "Berätta något om Stockholm!")],
    )
    assert c["sessions"] == [8]
    assert "MYAI_APP_LAB_ASR_V2: other-nonempty-final" in out
    assert "Stockholm" not in out


@pytest.mark.parametrize("events,expected", [
    ([], "no-final"),
    ([Event("partial_text", "privat")], "no-final"),
    ([Event("full_text", " ")], "invalid-final"),
    ([Event("full_text", "SECRET\x00")], "invalid-final"),
    ([Event("full_text", "x" * 241)], "invalid-final"),
    ([Event("unknown", "SECRET")], "unexpected-event"),
    ([Event("partial_text", "SECRET")] * 65, "event-budget-rejected"),
])
def test_fail_closed_synthetic_events(monkeypatch, capsys, events, expected):
    c, streams, out = execute(monkeypatch, capsys, events)
    assert c["sessions"] == [8]
    assert c["cancelled"] == 1
    assert c["mic_started"] == c["mic_stopped"] == 1
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_ASR_V2: " + expected
    assert "SECRET" not in out
    assert streams[0].exited == 1


def test_microphone_start_failure_never_calls_asr(monkeypatch, capsys):
    c, s, out = execute(monkeypatch, capsys, mic_start_fails=True)
    assert c["sessions"] == [] and s == []
    assert c["mic_started"] == c["mic_stopped"] == 1
    assert out.strip() == "MYAI_APP_LAB_ASR_V2: microphone-open-failed"
    assert "PRIVATE" not in out


def test_asr_failure_after_mic_open_releases(monkeypatch, capsys):
    c, s, out = execute(monkeypatch, capsys, asr_fails=True)
    assert c["sessions"] == [8] and s == []
    assert c["mic_stopped"] == 1
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_ASR_V2: asr-session-failed"
    assert "PRIVATE" not in out


def test_stream_close_error_discards_success(monkeypatch, capsys):
    c, streams, out = execute(
        monkeypatch, capsys,
        [Event("full_text", "Vad heter du?")],
        stream_exit_fails=True,
    )
    assert out.strip().splitlines()[-1] == (
        "MYAI_APP_LAB_ASR_V2: asr-session-failed"
    )
    assert c["mic_stopped"] == c["cancelled"] == 1
    assert streams[0].exited == 1


def test_cancel_failure_never_reports_success(monkeypatch, capsys):
    c, _, out = execute(monkeypatch, capsys,
                        [Event("full_text", "Vad heter du?")],
                        cancel_fails=True)
    assert out.strip().splitlines()[-1] == "MYAI_APP_LAB_ASR_V2: asr-cancel-failed"
    assert c["mic_stopped"] == 1


def test_mic_release_failure_never_reports_success(monkeypatch, capsys):
    c, _, out = execute(monkeypatch, capsys,
                        [Event("full_text", "Vad heter du?")],
                        mic_stop_fails=True)
    assert out.strip().splitlines()[-1] == (
        "MYAI_APP_LAB_ASR_V2: microphone-release-failed"
    )
    assert c["mic_stopped"] == 1
