"""Dependency inventory is read-only and cannot authorize device access."""
import json
import pytest
from scripts import ventuno_voice_dependency_inventory as inv


def test_versions_are_assembled_without_importing_any_module():
    checked = []
    def check(module):
        checked.append(module)
        return object()
    def version(name):
        return "1.2.3+cpu"
    result = inv.inspect(spec_finder=check, version_reader=version)
    assert checked == list(inv.VOICE_DISTRIBUTIONS)
    assert result["all_four_top_level_requirements_present"] is True
    assert result["status"] == "metadata-voice-dependencies-listed"
    assert result["dependency_wheel_hashes_locked"] is False
    assert result["voice_execution_authorized"] is False
    assert result["native_audio_backend_abi_verified"] is False
    assert result["packages_installed_by_this_check"] is False


def test_missing_optional_audio_module_blocks_dependency_completion():
    result = inv.inspect(
        spec_finder=lambda name: object() if name != "sounddevice" else None,
        version_reader=lambda name: "1.0",
    )
    assert result["status"] == "blocked-voice-dependencies-incomplete"
    assert result["voice_import_specs_found"]["sounddevice"] is False


def test_distribution_absent_even_when_module_spec_present_fails_closed():
    def version(name):
        if name == "faster-whisper":
            raise inv.importlib.metadata.PackageNotFoundError(name)
        return "1.0"
    result = inv.inspect(spec_finder=lambda _: object(), version_reader=version)
    assert result["installed_distribution_versions"]["faster_whisper"] is None
    assert result["all_four_top_level_requirements_present"] is False


def test_version_strings_cannot_export_private_text():
    result = inv.inspect(
        spec_finder=lambda _: object(),
        version_reader=lambda _: "SECRET_PRIVATE_PATH\nGITHUB_TOKEN=leaked",
    )
    assert "SECRET" not in json.dumps(result)
    assert result["all_four_top_level_requirements_present"] is False


def test_inventory_never_loads_native_audio(monkeypatch, capsys):
    monkeypatch.setattr(
        inv.importlib.util, "find_spec", lambda _: None,
    )
    monkeypatch.setattr(
        inv.importlib.metadata, "version",
        lambda name: (_ for _ in ()).throw(
            inv.importlib.metadata.PackageNotFoundError(name)
        ),
    )
    assert inv.main() == 0
    raw = capsys.readouterr().out
    report = json.loads(raw.partition("=")[2])
    assert report["status"] == "blocked-voice-dependencies-incomplete"
    assert report["model_loaded"] is False
    assert report["npu_executed"] is False
    assert report["voice_execution_authorized"] is False
