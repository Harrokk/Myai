"""Synthetic offline wheel artifacts, no downloads or actual imports."""
import hashlib
import json
import pytest
from scripts import ventuno_voice_wheelhouse_gate as gate


def create_set(folder, *, platform="manylinux_2_17_aarch64",
               python="cp312", tamper=None):
    folder.mkdir(parents=True, exist_ok=True)
    wheels = []
    for name in gate.REQUIRED:
        filename = f"{name}-1.0.0-{python}-none-{platform}.whl"
        path = folder / filename
        content = b"FAKE_BINARY_NOT_A_REAL_WHEEL_" + name.encode()
        path.write_bytes(content)
        digest = hashlib.sha256(content).hexdigest()
        wheels.append({"filename": filename, "sha256": digest})
    if tamper == "checksum":
        wheels[0]["sha256"] = "0" * 64
    if tamper == "duplicate":
        wheels[-1] = wheels[0].copy()
    if tamper == "missing":
        wheels.pop()
    (folder / "wheelhouse.lock.json").write_text(json.dumps({
        "python": "cp312",
        "platform": "aarch64",
        "complete_dependency_closure": True,
        "wheels": wheels,
    }))
    return wheels


def test_absent_wheelhouse_does_not_allow_any_activity():
    result = gate.classify(None)
    assert result["status"] == "blocked-no-reviewed-wheelhouse"
    assert result["audio_authorized"] is False
    assert result["native_abi_tested"] is False
    assert result["wheelhouse_installed"] is False
    assert result["package_download_attempted"] is False


def test_four_hashed_binary_filenames_yield_metadata_only_not_abi(tmp_path):
    create_set(tmp_path)
    result = gate.classify(tmp_path)
    assert result["status"] == "reviewed-wheelhouse-hashes-and-tags-only"
    assert result["reviewed_packages"] == 4
    assert result["wheel_file_hashes_verified"] is True
    assert result["dependency_closure_verified"] is False
    assert result["native_abi_tested"] is False
    assert result["audio_authorized"] is False


@pytest.mark.parametrize("bad", ["checksum", "missing", "duplicate"])
def test_invalid_wheel_manifest_denied(tmp_path, bad):
    create_set(tmp_path, tamper=bad)
    assert gate.classify(tmp_path)["status"] == "blocked-no-reviewed-wheelhouse"


@pytest.mark.parametrize("platform,python", [
    ("manylinux_2_17_x86_64", "cp312"),
    ("win_amd64", "cp312"),
    ("manylinux_2_17_aarch64", "cp310"),
    ("manylinux_2_17_armv7l", "cp312"),
])
def test_wrong_python_or_platform_tag_fails_closed(tmp_path, platform, python):
    create_set(tmp_path, platform=platform, python=python)
    assert gate.classify(tmp_path)["status"] == "blocked-no-reviewed-wheelhouse"


def test_symlink_and_deleted_wheels_denied(tmp_path):
    create_set(tmp_path)
    filenames = sorted(p for p in tmp_path.glob("*.whl"))
    filenames[0].unlink()
    filenames[0].symlink_to(filenames[1])
    assert gate.classify(tmp_path)["status"] == "blocked-no-reviewed-wheelhouse"


def test_invalid_manifest_json_does_not_expose_raw_values(tmp_path):
    tmp_path.joinpath("wheelhouse.lock.json").write_text(
        '{"secret":"PRIVATE_PACKAGE_URL_AND_TOKEN"}'
    )
    response = json.dumps(gate.classify(tmp_path))
    assert "PRIVATE" not in response
    assert "blocked" in response
