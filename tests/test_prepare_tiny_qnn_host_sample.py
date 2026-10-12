"""Host-only tiny QNN ONNX fixture is inert on VENTUNO Q."""
import json
import struct

import pytest

from scripts.prepare_tiny_qnn_host_sample import (
    INPUT_COUNT, INPUT_SHAPE, build_onnx_model, create_host_sample,
    input_values, is_ventuno_arch, raw_input_data, validate_new_output_dir,
)


def test_native_host_inputs_exact_and_deterministic():
    raw = raw_input_data()
    assert len(raw) == 4 * INPUT_COUNT == 256
    decoded = struct.unpack("<64f", raw)
    assert decoded == input_values()
    assert INPUT_SHAPE == (1, 1, 8, 8)
    assert all(-1 < v < 1 for v in decoded)


def test_arm_targets_refuse_host_model_generation(tmp_path):
    for machine in ("aarch64", "AARCH64", "arm64", "armv8l"):
        target = tmp_path / ("probe-" + machine)
        with pytest.raises(RuntimeError, match="host-only"):
            create_host_sample(target, machine=machine)
        assert not target.exists()


def test_host_path_rejects_existing_destination(tmp_path):
    directory = tmp_path / "already"
    directory.mkdir()
    with pytest.raises(ValueError, match="already-exists"):
        validate_new_output_dir(directory)


def test_parent_folder_must_exist(tmp_path):
    with pytest.raises(ValueError, match="existing-ordinary-directory"):
        validate_new_output_dir(tmp_path / "absent" / "fixture")


def test_reject_model_cache_destination(tmp_path):
    parent = tmp_path / ".cache"
    parent.mkdir()
    with pytest.raises(ValueError, match="model-or-service-tree"):
        validate_new_output_dir(parent / "tiny")


def test_model_generation_only_if_explicit_host_dependency_installed():
    onnx = pytest.importorskip("onnx")
    model = build_onnx_model()
    onnx.checker.check_model(model)
    assert len(model.graph.node) == 7
    assert [n.op_type for n in model.graph.node] == [
        "QuantizeLinear", "DequantizeLinear", "DequantizeLinear",
        "Conv", "Relu", "QuantizeLinear", "DequantizeLinear",
    ]
    assert model.ir_version == 8


def test_host_generation_writes_small_input_but_never_qnn_context(tmp_path):
    pytest.importorskip("onnx")
    directory = tmp_path / "tiny"
    info = create_host_sample(directory, machine="x86_64")
    assert info["qnn_converted"] is False
    assert info["htp_execution_measured"] is False
    assert info["qnn_context_compatible_with_target"] is False
    assert (directory / "input.raw").read_bytes() == raw_input_data()
    assert (directory / "input_list.txt").read_text() == "input:=input.raw\n"
    assert (directory / "tiny_qdq_conv.onnx").stat().st_size > 0
    assert json.loads((directory / "fixture_metadata.json").read_text()) == info
    assert not (directory / "context.bin").exists()
