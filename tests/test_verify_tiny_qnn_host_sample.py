"""Host-side CPU numerical validation of tiny ONNX QDQ fixture."""
import json

import pytest

from scripts.prepare_tiny_qnn_host_sample import create_host_sample
from scripts.verify_tiny_qnn_host_sample import verify_fixture


def test_full_onnx_reference_oracle_matches(tmp_path):
    pytest.importorskip("onnx")
    pytest.importorskip("numpy")
    folder = tmp_path / "fixture"
    create_host_sample(folder, machine="x86_64")
    result = verify_fixture(folder, machine="x86_64")
    assert result["onnx_checker_passed"] is True
    assert result["onnxruntime_cpu_executed"] is True
    assert result["independent_numpy_oracle_matched"] is True
    assert result["output_tensor_shape"] == [1, 1, 8, 8]
    assert 0 < result["nonzero_output_elements"] < 64
    assert result["qnn_conversion_verified"] is False
    assert result["htp_profile_measured"] is False
    assert result["production_services_modified"] is False


def test_host_onnx_reference_is_deterministic(tmp_path):
    pytest.importorskip("onnx")
    pytest.importorskip("numpy")
    folder = tmp_path / "fixture"
    create_host_sample(folder, machine="x86_64")
    first = verify_fixture(folder, machine="x86_64")
    second = verify_fixture(folder, machine="x86_64")
    assert first["reference_output_sha256"] == second["reference_output_sha256"]
    assert first["onnx_sha256"] == second["onnx_sha256"]


def test_host_onnx_validator_rejects_changed_raw_input(tmp_path):
    folder = tmp_path / "fixture"
    folder.mkdir()
    (folder / "tiny_qdq_conv.onnx").write_bytes(b"not a model")
    (folder / "input.raw").write_bytes(b"x" * 256)
    (folder / "input_list.txt").write_text("input:=input.raw\n")
    (folder / "fixture_metadata.json").write_text(json.dumps({
        "onnx_graph_checked": True,
        "qnn_converted": False,
        "htp_execution_measured": False,
    }))
    with pytest.raises(ValueError, match="fixture-input-mismatch"):
        verify_fixture(folder, machine="x86_64")


def test_host_onnx_validator_rejects_arm_even_with_file(tmp_path):
    with pytest.raises(RuntimeError, match="host-only-refuse-arm-target"):
        verify_fixture(tmp_path, machine="aarch64")


def test_host_onnx_validator_rejects_missing_folder(tmp_path):
    with pytest.raises(ValueError, match="invalid-fixture-directory"):
        verify_fixture(tmp_path / "not-present", machine="x86_64")
