"""Static wheel source pin audit is pure and never imports/writes packages."""
import json
from scripts import ventuno_voice_static_lock_check as gate


def test_committed_arm64_whisper_voice_wheel_lock_is_consistent():
    result = gate.inspect()
    assert result["status"] == "arm64-source-wheel-lock-coherent"
    assert result["pinned_wheel_records"] == 28
    assert result["source_lock_consistent"] is True
    assert result["packages_installed"] is False
    assert result["dependency_import_abi_verified"] is False
    assert result["voice_authorized"] is False


def test_changed_pin_or_hash_fails_closed(tmp_path):
    source = gate.ROOT / "config/voice_arm64_cp312_wheels.lock.json"
    original = json.loads(source.read_text())
    folder = tmp_path / "config"
    folder.mkdir()
    target = folder / source.name
    target.write_text(json.dumps(original))
    requirements = tmp_path / "requirements-voice-arm64-hashed.lock"
    requirements.write_text(
        (gate.ROOT / "requirements-voice-arm64-hashed.lock").read_text()
    )
    assert gate.inspect(tmp_path)["source_lock_consistent"]
    modified = json.loads(target.read_text())
    modified["wheels"][0]["sha256"] = "f" * 64
    target.write_text(json.dumps(modified))
    assert gate.inspect(tmp_path)["status"] == "blocked-unreviewed-wheel-lock"


def test_missing_or_symlinked_lock_fails_closed(tmp_path):
    folder = tmp_path / "config"
    folder.mkdir()
    target = folder / "voice_arm64_cp312_wheels.lock.json"
    target.symlink_to(gate.ROOT / "config/voice_arm64_cp312_wheels.lock.json")
    assert gate.inspect(tmp_path)["source_lock_consistent"] is False


def test_no_real_wheel_file_or_model_is_needed():
    assert gate.inspect()["model_loaded"] is False
    assert gate.inspect()["live_pypi_artifacts_reverified"] is False
