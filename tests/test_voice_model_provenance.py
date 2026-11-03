"""Pinned offline STT model integrity: synthetic bytes only, no downloads."""
import hashlib
import os

import pytest

from core.voice_model_provenance import (
    VerifiedSTTModel, verify_stt_model_files,
)


def fixture_model(tmp_path, *, filename="encoder.int8.onnx"):
    root = tmp_path / "model"
    root.mkdir()
    payload = b"synthetic-only-model-weights"
    path = root / filename
    path.write_bytes(payload)
    path.chmod(0o444)
    root.chmod(0o555)
    pinned = {filename: hashlib.sha256(payload).hexdigest()}
    return root, path, pinned


def test_trusted_readonly_files_produce_verified_bundle(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    bundle = verify_stt_model_files(
        root, family="parakeet", expected_sha256=pinned,
    )
    assert type(bundle) is VerifiedSTTModel
    assert bundle.root == str(root)
    assert bundle.family == "parakeet"
    assert bundle.revision.startswith("sha256:")
    assert len(bundle.revision) == len("sha256:") + 64
    assert bundle.is_current() is True


def test_raw_manifest_hash_with_wrong_bytes_is_rejected(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    pinned["encoder.int8.onnx"] = "a" * 64
    with pytest.raises(ValueError, match="stt-model-integrity-failed"):
        verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)


def test_immutable_bundle_cannot_be_relabelled(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    b = verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)
    with pytest.raises(AttributeError):
        b.family = "whisper"


def test_untrusted_direct_constructor_fails():
    with pytest.raises(ValueError, match="untrusted-model-identity"):
        VerifiedSTTModel(
            token=object(), root="/tmp", family="whisper",
            revision="sha256:" + "a" * 64, states=[("x", ())],
        )


def test_model_mutation_after_verification_invalidates_bundle(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    b = verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)
    path.chmod(0o644)
    path.write_bytes(b"tampered-model-bytes")
    path.chmod(0o444)
    assert b.is_current() is False


def test_readonly_permissions_must_remain_readonly(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    b = verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)
    path.chmod(0o644)
    assert b.is_current() is False


def test_symlinked_model_file_is_rejected(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    alt = tmp_path / "other.onnx"
    alt.write_bytes(path.read_bytes())
    root.chmod(0o755)
    path.unlink()
    path.symlink_to(alt)
    root.chmod(0o555)
    with pytest.raises(ValueError, match="stt-model-integrity-failed"):
        verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)


def test_symlinked_model_root_is_rejected(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    alias = tmp_path / "alias"
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        verify_stt_model_files(alias, family="parakeet", expected_sha256=pinned)


@pytest.mark.parametrize("filename", [
    "../weights.onnx", "/etc/passwd", ".", "..", "a/b", "",
    "weights\x00.onnx",
])
def test_invalid_filename_or_traversal_is_rejected(tmp_path, filename):
    root, path, pinned = fixture_model(tmp_path)
    with pytest.raises(ValueError, match="stt-model-integrity-failed"):
        verify_stt_model_files(
            root, family="parakeet", expected_sha256={filename: "a"*64},
        )


def test_root_must_not_be_writable(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    root.chmod(0o755)
    with pytest.raises(ValueError):
        verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)


def test_model_file_must_not_be_writable(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    path.chmod(0o644)
    with pytest.raises(ValueError):
        verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)


def test_aliasing_hardlinked_file_is_rejected(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    os.link(path, tmp_path / "other")
    with pytest.raises(ValueError):
        verify_stt_model_files(root, family="parakeet", expected_sha256=pinned)


@pytest.mark.parametrize("family", [
    None, "Parakeet", "p", "../../bad", "x"*65,
])
def test_invalid_model_family_rejected(tmp_path, family):
    root, path, pinned = fixture_model(tmp_path)
    with pytest.raises(ValueError, match="stt-model-integrity-failed"):
        verify_stt_model_files(root, family=family, expected_sha256=pinned)


def test_generic_error_does_not_disclose_model_path(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    with pytest.raises(ValueError) as err:
        verify_stt_model_files(root, family="parakeet", expected_sha256={
            "encoder.int8.onnx": "0" * 64,
        })
    assert str(root) not in str(err.value)


def test_no_file_open_when_manifest_is_missing(tmp_path):
    root, path, pinned = fixture_model(tmp_path)
    with pytest.raises(ValueError):
        verify_stt_model_files(root, family="parakeet", expected_sha256={})
