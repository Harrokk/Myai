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


def test_pinned_faster_whisper_rejects_pyav_19_even_when_hashes_match(tmp_path):
    """PyAV 19 removes metadata_errors used by faster-whisper 1.2.1."""
    import json
    folder = tmp_path / "config"
    folder.mkdir()
    original = json.loads(
        (gate.ROOT / "config/voice_arm64_cp312_wheels.lock.json").read_text()
    )
    rows = original["wheels"]
    av = next(row for row in rows if row["filename"].startswith("av-"))
    assert av["filename"].startswith("av-18.")
    av["filename"] = av["filename"].replace("av-18.1.0-", "av-19.0.1-")
    av["sha256"] = "a" * 64
    (folder / "voice_arm64_cp312_wheels.lock.json").write_text(
        json.dumps(original)
    )
    requirements = (gate.ROOT / "requirements-voice-arm64-hashed.lock").read_text()
    requirements = requirements.replace("av==18.1.0", "av==19.0.1")
    original_hash = next(
        line.partition("sha256:")[2] for line in requirements.splitlines()
        if line.startswith("av==19.0.1")
    )
    requirements = requirements.replace(original_hash, "a" * 64)
    (tmp_path / "requirements-voice-arm64-hashed.lock").write_text(
        requirements
    )
    assert gate.inspect(tmp_path)["status"] == "blocked-unreviewed-wheel-lock"
