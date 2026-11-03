"""Opt-in Parakeet SHA256 loader contracts; tiny test data, no native model."""
import hashlib

import pytest

from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT
from core.voice_model_provenance import VerifiedSTTModel


def synthetic_bundle(tmp_path):
    root = tmp_path / "parakeet"
    root.mkdir()
    manifest = {}
    for filename in SherpaOnnxParakeetSTT.MODEL_FILES:
        data = ("fixture:" + filename).encode()
        file = root / filename
        file.write_bytes(data)
        file.chmod(0o444)
        manifest[filename] = hashlib.sha256(data).hexdigest()
    root.chmod(0o555)
    return root, manifest


def test_prepare_verified_model_does_not_import_or_load_native_model(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    bundle = stt.prepare_verified_model()
    assert type(bundle) is VerifiedSTTModel
    assert bundle.family == "parakeet"
    assert bundle.root == str(root)
    assert bundle.is_current() is True
    assert stt._model is None
    assert stt._module is None


def test_manifest_must_include_every_required_model_file(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    del manifest["tokens.txt"]
    with pytest.raises(ValueError, match="Invalid trusted"):
        SherpaOnnxParakeetSTT(
            model_name=str(root), trusted_model_file_hashes=manifest,
        )


def test_incorrect_model_digest_is_rejected_before_native_load(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    manifest["joiner.int8.onnx"] = "0" * 64
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    with pytest.raises(RuntimeError, match="integrity check failed"):
        stt.prepare_verified_model()
    assert stt._model is None


def test_writable_model_files_are_denied(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    (root / "encoder.int8.onnx").chmod(0o644)
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    with pytest.raises(RuntimeError, match="integrity check failed"):
        stt.prepare_verified_model()


def test_mutation_invalidates_previously_verified_bundle(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    bundle = stt.prepare_verified_model()
    path = root / "tokens.txt"
    path.chmod(0o644)
    path.write_bytes(b"changed-source")
    path.chmod(0o444)
    assert bundle.is_current() is False
    with pytest.raises(RuntimeError, match="integrity check failed"):
        stt.prepare_verified_model()


def test_cannot_supply_unverified_native_model_with_trusted_manifest(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    with pytest.raises(ValueError, match="Invalid trusted"):
        SherpaOnnxParakeetSTT(
            model_name=str(root),
            trusted_model_file_hashes=manifest,
            model=object(),
        )


def test_non_pinned_existing_parakeet_path_remains_default(tmp_path):
    stt = SherpaOnnxParakeetSTT(model_name=str(tmp_path))
    assert stt._trusted_model_file_hashes is None
    assert stt._verified_model_bundle is None
    with pytest.raises(RuntimeError, match="trusted model manifest"):
        stt.prepare_verified_model()


def test_untrusted_runtime_mutation_of_caller_manifest_cannot_repin(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    manifest["tokens.txt"] = "0" * 64
    assert stt.prepare_verified_model().is_current()


def test_symlinked_tokens_file_refused_by_pinned_preflight(tmp_path):
    root, manifest = synthetic_bundle(tmp_path)
    alt = tmp_path / "target"
    alt.write_bytes((root / "tokens.txt").read_bytes())
    path = root / "tokens.txt"
    root.chmod(0o755)
    path.unlink()
    path.symlink_to(alt)
    root.chmod(0o555)
    stt = SherpaOnnxParakeetSTT(
        model_name=str(root), trusted_model_file_hashes=manifest,
    )
    with pytest.raises(RuntimeError, match="missing or incomplete"):
        stt.prepare_verified_model()
