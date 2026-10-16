"""Only synthetic import paths; live ABI is tested in disposable ARM venv."""
import json
from scripts import ventuno_disposable_voice_abi as abi


def test_unknown_module_rejected_before_any_import(monkeypatch):
    monkeypatch.setattr(abi.importlib, "import_module", lambda *_: 1 / 0)
    result = abi.check("untrusted")
    assert result["status"] == "blocked-unknown-module"
    assert result["audio_device_opened"] is False


def test_import_result_remains_sanitized_and_does_not_initialize_tts(monkeypatch):
    calls = []
    monkeypatch.setattr(abi.importlib, "import_module",
                        lambda name: calls.append(name) or object())
    monkeypatch.setattr(abi.importlib.metadata, "version", lambda _: "1.2")
    result = abi.check("sounddevice")
    assert calls == ["sounddevice"]
    assert result["native_abi_import_accepted"] is True
    assert result["model_loaded"] is False
    assert result["audio_device_opened"] is False
    assert result["tts_engine_initialized"] is False
    assert result["npu_tested"] is False
    assert "/home/arduino" not in json.dumps(result)


def test_failed_import_does_not_report_success_or_exception(monkeypatch):
    def reject(_):
        raise OSError("private board installation path and token")
    monkeypatch.setattr(abi.importlib, "import_module", reject)
    result = abi.check("ctranslate2")
    assert result["status"] == "blocked-native-module-import"
    assert result["native_abi_import_accepted"] is False
    assert "private board" not in json.dumps(result)
