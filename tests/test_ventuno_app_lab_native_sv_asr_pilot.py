"""Only stdlib/static fake-SDK tests; the ASR pilot is never actually run."""
from pathlib import Path
from types import ModuleType
import re
import runpy
import sys

APP = (Path(__file__).resolve().parents[1] /
       "integrations/arduino_app_lab/myai_sv_asr_once")
SOURCE = APP / "python/main.py"


def _fake_arduino(monkeypatch, transcript, *, fail=False):
    counts = {"created": 0, "transcribe": [], "registered": 0}
    top = ModuleType("arduino")
    pkg = ModuleType("arduino.app_bricks")
    asr_pkg = ModuleType("arduino.app_bricks.asr")
    utils = ModuleType("arduino.app_utils")

    class ASR:
        def __init__(self, *, language):
            counts["created"] += 1
            assert language == "sv"

        def transcribe(self, *, duration):
            counts["transcribe"].append(duration)
            if fail:
                raise RuntimeError("PRIVATE_TRANSCRIPT_IN_EXCEPTION")
            return transcript

    class App:
        @staticmethod
        def run(*, user_loop):
            counts["registered"] += 1
            try:
                user_loop()
            except StopIteration:
                pass
            # Ensure the callback cannot record a second time.
            try:
                user_loop()
            except StopIteration:
                pass

    asr_pkg.AutomaticSpeechRecognition = ASR
    utils.App = App
    for name, value in {
        "arduino": top, "arduino.app_bricks": pkg,
        "arduino.app_bricks.asr": asr_pkg, "arduino.app_utils": utils,
    }.items():
        monkeypatch.setitem(sys.modules, name, value)
    return counts


def test_app_uses_only_first_party_asr_and_no_web_ui_or_llm():
    manifest = (APP / "app.yaml").read_text(encoding="utf-8")
    assert "bricks:\\n  - arduino:asr" in manifest
    assert "arduino:web_ui" not in manifest and "arduino:llm" not in manifest
    code = SOURCE.read_text(encoding="utf-8")
    assert 'AutomaticSpeechRecognition(language="sv")' in code
    assert "App.run(user_loop=run_one_diagnostic)" in code
    assert "chat(" not in code and "speak(" not in code
    assert "web_ui" not in code and "requests" not in code


def test_once_for_expected_swedish_words(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "Vad heter du?")
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert counts == {"created": 1, "transcribe": [5], "registered": 1}
    assert "reference-recognized" in out
    assert "Vad heter du?" not in out


def test_other_text_never_logged_or_replayed(monkeypatch, capsys):
    counts = _fake_arduino(monkeypatch, "Jag gillar pommes frites!")
    runpy.run_path(str(SOURCE), run_name="__main__")
    out = capsys.readouterr().out
    assert "other-nonempty-text" in out
    assert "pommes" not in out
    assert counts["transcribe"] == [5]


def test_no_speech_and_exception_keep_private_words_hidden(monkeypatch, capsys):
    for transcript, fail in (("", False), ("SECRET_WORDS", True)):
        counts = _fake_arduino(monkeypatch, transcript, fail=fail)
        runpy.run_path(str(SOURCE), run_name="__main__")
        out = capsys.readouterr().out
        assert "SECRET_WORDS" not in out
        assert "PRIVATE_TRANSCRIPT" not in out
        assert counts["transcribe"] == [5]
