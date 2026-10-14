"""Verify exact synthetic ONNX graph contract on an isolated x86 host.

No QNN SDK import, HTP model preparation, NPU inference or device access.
ONNX schema and exact Q/DQ+Conv+Relu topology are source-level evidence,
NOT vendor HTP-v75 operator acceptance. No raw tensor data is emitted.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform

from scripts.qairt_host_toolchain_preflight import (
    EXPECTED_SHA256, EXPECTED_MODEL_SIZE,
)
from scripts.prepare_tiny_qnn_host_sample import is_ventuno_arch

EXPECTED_OPS = (
    "QuantizeLinear", "DequantizeLinear", "DequantizeLinear",
    "Conv", "Relu", "QuantizeLinear", "DequantizeLinear",
)
EXPECTED_TENSOR_SHAPE = (1, 1, 8, 8)
EXPECTED_WEIGHTS = (0, 1, 0, 1, 4, 1, 0, 1, 0)
MAX_ONNX_BYTES = 4096


def initial_report():
    return {
        "probe": "tiny_qdq_offhost_onnx_contract_only",
        "status": "not_checked",
        "source_sha256_verified": False,
        "onnx_schema_verified": False,
        "exact_expected_op_sequence_verified": False,
        "exact_qdq_tensor_contract_verified": False,
        "static_quantization_parameters_verified": False,
        "htp_v75_operator_support_verified": False,
        "htp_prepare_or_context_generated": False,
        "htp_placement_verified": False,
        "qnn_or_npu_executed": False,
        "production_modified": False,
        "raw_tensor_names_data_or_paths_exported": False,
    }


def tensor_matches(tensor, data_type, dims, values, numpy_helper):
    try:
        if tensor.data_type != data_type or tuple(tensor.dims) != tuple(dims):
            return False
        arr = numpy_helper.to_array(tensor)
        if arr.size != len(values):
            return False
        return all(float(a) == float(b) for a, b in zip(arr.flat, values))
    except (TypeError, ValueError, RuntimeError):
        return False


def topology_is_exact(graph):
    expected = (
        ("QuantizeLinear", ("input", "x_scale", "x_zero"), ("x_quant",)),
        ("DequantizeLinear", ("x_quant", "x_scale", "x_zero"), ("x_dequant",)),
        ("DequantizeLinear", ("w_i8", "w_scale", "w_zero"), ("w_dequant",)),
        ("Conv", ("x_dequant", "w_dequant"), ("conv",)),
        ("Relu", ("conv",), ("relu",)),
        ("QuantizeLinear", ("relu", "y_scale", "y_zero"), ("y_quant",)),
        ("DequantizeLinear", ("y_quant", "y_scale", "y_zero"), ("output",)),
    )
    if len(graph.node) != len(expected):
        return False
    for node, (op, inputs, outputs) in zip(graph.node, expected):
        if (node.domain not in ("", "ai.onnx") or node.op_type != op
                or tuple(node.input) != inputs or tuple(node.output) != outputs):
            return False
    convolution = graph.node[3]
    if len(convolution.attribute) != 1:
        return False
    attribute = convolution.attribute[0]
    return attribute.name == "pads" and tuple(attribute.ints) == (1, 1, 1, 1)


def io_shape_is_expected(value, tensor_type):
    try:
        info = value.type.tensor_type
        dims = tuple(int(d.dim_value) for d in info.shape.dim)
        return info.elem_type == tensor_type and dims == EXPECTED_TENSOR_SHAPE
    except (AttributeError, ValueError, TypeError):
        return False


def inspect_model(path: Path, *, machine: str | None = None):
    result = initial_report()
    if is_ventuno_arch(machine or platform.machine()):
        result["status"] = "no_go_target_architecture"
        return result
    try:
        if path.is_symlink() or not path.is_file():
            result["status"] = "fixture_unavailable"
            return result
        size = path.stat().st_size
        if size != EXPECTED_MODEL_SIZE or size > MAX_ONNX_BYTES:
            result["status"] = "fixture_size_mismatch"
            return result
        raw = path.read_bytes()
        if len(raw) != EXPECTED_MODEL_SIZE or hashlib.sha256(raw).hexdigest() != EXPECTED_SHA256:
            result["status"] = "fixture_digest_mismatch"
            return result
    except OSError:
        result["status"] = "fixture_unavailable"
        return result
    result["source_sha256_verified"] = True
    try:
        import onnx
        from onnx import TensorProto, numpy_helper
    except ImportError:
        result["status"] = "onnx_dependency_unavailable"
        return result
    try:
        model = onnx.load_model_from_string(raw)
        onnx.checker.check_model(model, full_check=True)
        result["onnx_schema_verified"] = True
        if model.ir_version != 8 or len(model.opset_import) != 1 or (
            model.opset_import[0].domain != "" or model.opset_import[0].version != 13
        ):
            result["status"] = "opset_or_ir_mismatch"
            return result
        graph = model.graph
        result["exact_expected_op_sequence_verified"] = topology_is_exact(graph)
        result["exact_qdq_tensor_contract_verified"] = (
            len(graph.input) == len(graph.output) == 1
            and io_shape_is_expected(graph.input[0], TensorProto.FLOAT)
            and io_shape_is_expected(graph.output[0], TensorProto.FLOAT)
            and graph.input[0].name == "input"
            and graph.output[0].name == "output"
        )
        initializers = {tensor.name: tensor for tensor in graph.initializer}
        expected = {
            "x_scale": (TensorProto.FLOAT, (), (1 / 32,)),
            "x_zero": (TensorProto.UINT8, (), (128,)),
            "w_i8": (TensorProto.INT8, (1, 1, 3, 3), EXPECTED_WEIGHTS),
            "w_scale": (TensorProto.FLOAT, (), (1 / 64,)),
            "w_zero": (TensorProto.INT8, (), (0,)),
            "y_scale": (TensorProto.FLOAT, (), (1 / 512,)),
            "y_zero": (TensorProto.UINT8, (), (0,)),
        }
        result["static_quantization_parameters_verified"] = (
            set(initializers) == set(expected)
            and all(
                tensor_matches(initializers[name], dtype, dims, vals, numpy_helper)
                for name, (dtype, dims, vals) in expected.items()
            )
        )
        result["status"] = (
            "source_onnx_contract_verified_not_htp_support"
            if result["exact_expected_op_sequence_verified"]
            and result["exact_qdq_tensor_contract_verified"]
            and result["static_quantization_parameters_verified"]
            else "graph_contract_mismatch"
        )
    except (OSError, ValueError, TypeError, RuntimeError):
        result["status"] = "onnx_checker_or_parse_failure"
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, type=Path)
    args = parser.parse_args()
    result = inspect_model(args.model)
    print("MYAI_OFFHOST_QDQ_CONTRACT_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["status"] == "source_onnx_contract_verified_not_htp_support" else 2


if __name__ == "__main__":
    raise SystemExit(main())
