"""No real Arduino SDK imported, no microphone or local NPU opened."""
from pathlib import Path
from types import ModuleType
import runpy
import sys

APP = (Path(__file__).resolve().parents[1] /
       "integrations/arduino_app_lab/myai_sv_asr_once")
SOURCE = APP / "python/main.py"


def _fake_arduino(monkeypatch, transcript, *, fail=False,
                  start_fails=False, stop_fails=False):
    audit = []
    counts = {"created": 0, "transcribe": [], "registered": 0,
              "mic_starts": 0, "mic_stops": 0, "audit": audit}
    top = ModuleType("arduino")
    pkg = ModuleType("arduino.app_bricks")
    asr_pkg = ModuleType("arduino.app_bricks.asr")
    utils = ModuleType("arduino.app_utils")
    peripheral = ModuleType("arduino.app_peripherals")
    microphones = ModuleType("arduino.app_peripherals.microphone")

    class Microphone:
        def __init__(self, *, device, shared, auto_reconnect):
            assert device == "plughw:1,0"
            assert shared is False
            assert auto_reconnect is False
            self.running = False
            counts["device"] = device
            audit.append("construct-mic")

        def start(self):
            counts["mic_starts"] += 1
            audit.append("mic-start")
            if start_fails:
                raise RuntimeError("PRIVATE_MIC_ERROR")
            self.running = True

        def stop(self):
            counts["mic_stops"] += 1
            audit.append("mic-stop")
            self.running = False
            if stop_fails:
                raise RuntimeError("PRIVATE_RELEASE_ERROR")

    class ASR:
        def __init__(self, *, mic, language):
            assert isinstance(mic, Microphone)
            assert language == "sv"
            self.mic = mic
            counts["created"] += 1
            audit.append("construct-asr")

        def transcribe(self, *, duration):
            assert self.mic.running, "caller-owned mic must already be started"
            counts["transcribe"].append(duration)
            audit.append("transcribe")
            if fail:
                raise RuntimeError("PRIVATE_TRANSCRIPT_IN_EXCEPTION")
            return transcript

    class App:
        @staticmethod
        def run(*, user_loop):
            counts["registered"] += 1
            audit.append("app-run")
            # Arduino has finished its Brick startup before user_loop.
            for _ in range(2):
                try:
                    user_loop()
                except StopIteration:
                    pass

    asr_pkg.AutomaticSpeechRecognition = ASR
    microphones.Microphone = Microphone
    utils.App = App
    for name, value in {
        "arduino": top, "arduino.app_bricks": pkg,
        "arduino.app_bricks.asr": asr_pkg, "arduino.app_utils": utils,
        "arduino.app_peripherals": peripheral,
        "arduino.app_peripherals.microphone": microphones,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    return counts


def test_only_first_party_asr_and_explicit_already_verified_usb_mic():
    manifest = (APP / "app.yaml").read_text(encoding="utf-8")
    assert "bricks:\n  - arduino:asr" in manifest
    assert "arduino:web_ui" not in manifest and "arduino:llm" not in manifest
    code = SOURCE.read_text(encoding="utf-8")
    assert 'Microphone(device="plughw:1,0", shared=False, auto_reconnect=False)' in code
    assert 'AutomaticSpeechRecognition(mic=mic, language="sv")' in code
    assert "mic.start()" in code and "mic.stop()" in code
    assert "App.run(user_loop=run_one_diagnostic)" in code
    assert "chat(" not in code and "speak(" not in code
    assert "web_ui" not in code and "requests" not in code


def test_one_swedish_phrase_opens_exactly_one_microphone_and_releases(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "Vad heter du?")
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert counts["transcribe"] == [5]
    assert counts["mic_starts"] == 1 and counts["mic_stops"] == 1
    assert counts["audit"] == [
        "construct-mic", "construct-asr", "app-run",
        "mic-start", "transcribe", "mic-stop",
    ]
    assert "reference-recognized" in out
    assert "Vad heter du?" not in out


def test_different_sentence_never_leaked_or_replayed(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "Jag gillar pommes frites!")
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert "other-nonempty-text" in out and "pommes" not in out
    assert counts["transcribe"] == [5]
    assert counts["mic_starts"] == counts["mic_stops"] == 1


def test_empty_result_and_recognizer_error_still_release(monkeypatch, capsys):
    for transcript, fail in (("", False), ("SECRET_WORDS", True)):
        counts = _fake_arduino(monkeypatch, transcript, fail=fail)
        runpy.run_path(str(SOURCE), run_name="__main__")
        out = capsys.readouterr().out
        assert "SECRET_WORDS" not in out and "PRIVATE_TRANSCRIPT" not in out
        assert counts["mic_starts"] == counts["mic_stops"] == 1
        assert counts["transcribe"] == [5]


def test_start_failure_does_not_transcribe_and_attempts_cleanup(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "SECRET", start_fails=True)
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert "unavailable-or-failed" in out and "SECRET" not in out
    assert counts["mic_starts"] == counts["mic_stops"] == 1
    assert counts["transcribe"] == []


def test_stop_failure_is_not_reported_as_success(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "Vad heter du?", stop_fails=True)
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert "microphone-release-failed" in out
    assert "reference-recognized" not in out
    assert counts["transcribe"] == [5]
    assert counts["mic_stops"] == 1
