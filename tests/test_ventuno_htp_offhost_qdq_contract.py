"""Static synthetic graph checks; no QNN, models on NPU or device access."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import ventuno_htp_offhost_qdq_contract as audit
from scripts import prepare_tiny_qnn_host_sample as source


def test_offboard_is_required(tmp_path):
    path = tmp_path / "unused"
    report = audit.inspect_model(path, machine="aarch64")
    assert report["status"] == "no_go_target_architecture"
    assert report["qnn_or_npu_executed"] is False


def test_missing_source_remains_unknown(tmp_path):
    report = audit.inspect_model(tmp_path / "missing.onnx", machine="x86_64")
    assert report["status"] == "fixture_unavailable"
    assert report["htp_v75_operator_support_verified"] is False


def test_corrupted_bytes_never_claim_source_identity(tmp_path):
    filename = tmp_path / "tiny.onnx"
    filename.write_bytes(b"x" * audit.EXPECTED_MODEL_SIZE)
    report = audit.inspect_model(filename, machine="x86_64")
    assert report["status"] == "fixture_digest_mismatch"
    assert report["source_sha256_verified"] is False


def test_tiny_onnx_model_is_not_a_vendor_htp_acceptance_certificate(tmp_path):
    onnx = pytest.importorskip("onnx")
    filename = tmp_path / "tiny.onnx"
    model = source.build_onnx_model()
    filename.write_bytes(model.SerializeToString())
    result = audit.inspect_model(filename, machine="x86_64")
    assert result["source_sha256_verified"] is True
    assert result["status"] == "source_onnx_contract_verified_not_htp_support"
    assert result["onnx_schema_verified"] is True
    assert result["exact_expected_op_sequence_verified"] is True
    assert result["exact_qdq_tensor_contract_verified"] is True
    assert result["static_quantization_parameters_verified"] is True
    assert result["htp_v75_operator_support_verified"] is False
    assert result["htp_prepare_or_context_generated"] is False
    assert result["htp_placement_verified"] is False
    assert result["qnn_or_npu_executed"] is False
    assert result["production_modified"] is False


def test_graph_topology_refuses_wrong_op_and_padding():
    expected = [
        ("QuantizeLinear", ("input", "x_scale", "x_zero"), ("x_quant",)),
        ("DequantizeLinear", ("x_quant", "x_scale", "x_zero"), ("x_dequant",)),
        ("DequantizeLinear", ("w_i8", "w_scale", "w_zero"), ("w_dequant",)),
        ("Conv", ("x_dequant", "w_dequant"), ("conv",)),
        ("Relu", ("conv",), ("relu",)),
        ("QuantizeLinear", ("relu", "y_scale", "y_zero"), ("y_quant",)),
        ("DequantizeLinear", ("y_quant", "y_scale", "y_zero"), ("output",)),
    ]
    nodes = [
        SimpleNamespace(op_type=op, domain="", input=ins, output=outs,
                        attribute=[SimpleNamespace(name="pads", ints=[1, 1, 1, 1])] if op == "Conv" else [])
        for op, ins, outs in expected
    ]
    assert audit.topology_is_exact(SimpleNamespace(node=nodes)) is True
    nodes[3].attribute[0].ints = [0, 0, 0, 0]
    assert audit.topology_is_exact(SimpleNamespace(node=nodes)) is False
    nodes[3].attribute[0].ints = [1, 1, 1, 1]
    nodes[4].op_type = "Sigmoid"
    assert audit.topology_is_exact(SimpleNamespace(node=nodes)) is False


def test_unsafe_or_oversize_source_cannot_be_loaded(tmp_path):
    path = tmp_path / "tiny.onnx"
    path.write_bytes(b"a" * (audit.MAX_ONNX_BYTES + 1))
    assert audit.inspect_model(path, machine="x86_64")["status"] == "fixture_size_mismatch"
    symlink = tmp_path / "model-link"
    symlink.symlink_to(path)
    assert audit.inspect_model(symlink, machine="x86_64")["status"] == "fixture_unavailable"


def test_report_never_asserts_htp_from_source_schema():
    r = audit.initial_report()
    assert r["htp_v75_operator_support_verified"] is False
    assert r["htp_prepare_or_context_generated"] is False
    assert r["htp_placement_verified"] is False
    assert r["qnn_or_npu_executed"] is False
    assert r["raw_tensor_names_data_or_paths_exported"] is False
