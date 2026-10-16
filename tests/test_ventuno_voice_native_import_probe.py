"""Synthetic metadata/import guard tests; no real native packages imported."""
import os

from scripts import ventuno_voice_native_import_probe as native


def test_never_import_native_code_without_disposable_venv(monkeypatch):
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    seen = []
    result = native.preflight(
        venv_prefix="/tmp/unused-venv",
        imports=lambda name: seen.append(name),
        lookup=lambda name: "1.2.3",
    )
    assert seen == []
    assert result["status"] == "blocked-disposable-voice-native-import"
    assert result["microphone_or_speaker_opened"] is False
    assert result["real_audio_authorized"] is False


def test_synthetic_disposable_env_imports_and_versions(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/myai-isolated-venv")
    observed = []
    def fake_import(name):
        observed.append(name)
        return object()
    report = native.preflight(
        venv_prefix="/tmp/myai-isolated-venv",
        imports=fake_import,
        lookup=lambda name: "1.2.3",
    )
    assert report["status"] == "disposable-native-import-check-passed"
    assert tuple(observed) == native.REQUIRED_MODULES
    assert report["verified_distribution_count"] == len(native.DISTRIBUTIONS)
    assert report["production_venv_modified"] is False
    assert report["npu_executed"] is False


def test_missing_library_fails_closed(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/tmp/myai-isolated-venv")
    def fake_import(name):
        if name == "ctranslate2":
            raise ImportError("PRIVATE_SYSTEM_PATH_SHOULD_NOT_BE_PRINTED")
        return object()
    result = native.preflight(
        venv_prefix="/tmp/myai-isolated-venv",
        imports=fake_import,
        lookup=lambda name: "1.2.3",
    )
    assert result["imports_passed"]["ctranslate2"] is False
    assert result["status"] == "blocked-disposable-voice-native-import"
    assert "PRIVATE_" not in str(result)


def test_production_venv_never_allowed(monkeypatch):
    monkeypatch.setenv("VIRTUAL_ENV", "/home/arduino/MyAI/.venv")
    called = []
    result = native.preflight(
        venv_prefix="/home/arduino/MyAI/.venv",
        imports=lambda name: called.append(name),
        lookup=lambda name: "1.2.3",
    )
    assert result["status"] == "blocked-disposable-voice-native-import"
    assert not called
