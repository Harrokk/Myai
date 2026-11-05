"""No physical Arduino import, microphone, ASR service, GenieX, or audio."""
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
            stream_exit_fails=False, cancel_fails=False):
    counts = {"initialized": 0, "sessions": [], "cancelled": 0, "calls": 0}
    top = ModuleType("arduino")
    bricks = ModuleType("arduino.app_bricks")
    asr_module = ModuleType("arduino.app_bricks.asr")
    utils = ModuleType("arduino.app_utils")
    streams = []

    class AutomaticSpeechRecognition:
        def __init__(self, *, language, translate):
            assert language == "sv"
            assert translate is False
            counts["initialized"] += 1

        def transcribe_sentence_stream(self, *, timeout):
            counts["sessions"].append(timeout)
            if asr_fails:
                raise RuntimeError("PRIVATE_RAW_TRANSCRIPT")
            s = FakeStream(events, exit_fails=stream_exit_fails)
            streams.append(s)
            return s

        def cancel(self):
            counts["cancelled"] += 1
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
    utils.App = App
    for name, obj in {
        "arduino": top, "arduino.app_bricks": bricks,
        "arduino.app_bricks.asr": asr_module, "arduino.app_utils": utils,
    }.items():
        monkeypatch.setitem(sys.modules, name, obj)
    runpy.run_path(str(SOURCE), run_name="__main__")
    return counts, streams, capsys.readouterr().out


def test_manifest_official_asr_only_and_no_old_pipeline():
    manifest = (APP / "app.yaml").read_text(encoding="utf-8")
    assert "bricks:\n  - arduino:asr" in manifest
    assert "arduino:llm" not in manifest
    assert "arduino:tts" not in manifest
    source = SOURCE.read_text(encoding="utf-8")
    for forbidden in (
        "ventuno_usb", "faster_whisper", "arecord", "aplay",
        "systemctl", "sudo", "GenieX", "OllamaClient", "requests",
        "whisper.tiny", "alsa.", "subprocess",
    ):
        assert forbidden not in source
    assert "transcribe_sentence_stream(timeout=MAX_SENTENCE_SECONDS)" in source
    assert 'AutomaticSpeechRecognition(language="sv", translate=False)' in source
    assert "asr.cancel()" in source
    assert "App.run(user_loop=run_one)" in source


def test_exact_swedish_phrase_one_final_one_session(monkeypatch, capsys):
    c, s, output = execute(
        monkeypatch, capsys,
        [Event("partial_text", "hemliga ord"),
         Event("full_text", "Vad heter du?"),
         Event("full_text", "second private phrase")],
    )
    assert c["initialized"] == 1
    assert c["sessions"] == [8]
    assert c["cancelled"] == 1
    assert len(s) == 1 and s[0].entered == s[0].exited == 1
    assert output.strip() == "MYAI_APP_LAB_ASR_V2: reference-recognized"
    assert "hemliga" not in output
    assert "second" not in output


def test_normal_natural_speech_is_reported_not_strict_phrase_denied(monkeypatch, capsys):
    c, _, output = execute(
        monkeypatch, capsys,
        [Event("full_text", "Berätta något om Stockholm!")],
    )
    assert c["sessions"] == [8]
    assert output.strip() == "MYAI_APP_LAB_ASR_V2: other-nonempty-final"
    assert "Stockholm" not in output


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
    assert out.strip() == "MYAI_APP_LAB_ASR_V2: " + expected
    assert "SECRET" not in out
    assert streams[0].exited == 1


def test_sdk_exception_never_logs_private_contents(monkeypatch, capsys):
    c, streams, out = execute(monkeypatch, capsys, asr_fails=True)
    assert out.strip() == "MYAI_APP_LAB_ASR_V2: asr-session-failed"
    assert "PRIVATE" not in out
    assert c["cancelled"] == 1
    assert streams == []


def test_stream_close_error_discards_any_success(monkeypatch, capsys):
    c, streams, out = execute(
        monkeypatch, capsys,
        [Event("full_text", "Vad heter du?")],
        stream_exit_fails=True,
    )
    assert out.strip() == "MYAI_APP_LAB_ASR_V2: asr-session-failed"
    assert streams[0].exited == 1
    assert c["cancelled"] == 1


def test_failed_cancel_cannot_report_success(monkeypatch, capsys):
    c, _, out = execute(
        monkeypatch, capsys,
        [Event("full_text", "Vad heter du?")],
        cancel_fails=True,
    )
    assert out.strip() == "MYAI_APP_LAB_ASR_V2: asr-cancel-failed"
    assert c["cancelled"] == 1
