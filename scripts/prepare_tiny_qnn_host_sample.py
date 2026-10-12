"""Prepare a tiny standalone ONNX candidate for later QAIRT/HTP conversion.

HOST-ONLY and explicitly invoked, never part of the automated device
diagnostics. No network access, QNN runtime call, model execution or changes
to production GenieX contexts. Requires `onnx` on a separate development host.

The Q/DQ Conv+ReLU graph is not guaranteed accepted by QAIRT 2.45 or to
execute on the HTP. Such claims require verified conversion and profiling.
"""
from __future__ import annotations

import argparse
import json
import platform
import struct
from pathlib import Path

INPUT_SHAPE = (1, 1, 8, 8)
INPUT_COUNT = 64
MODEL_NAME = "tiny_qdq_conv"


def is_ventuno_arch(machine: str) -> bool:
    return machine.strip().casefold() in {"aarch64", "arm64", "armv8l"}


def input_values() -> tuple[float, ...]:
    """Deterministic finite float32 input. No calibration or user input."""
    return tuple(((index % 13) - 6) / 32.0 for index in range(INPUT_COUNT))


def raw_input_data() -> bytes:
    return struct.pack("<" + "f" * INPUT_COUNT, *input_values())


def validate_new_output_dir(path: Path) -> None:
    """Avoid overwriting existing files, production caches or symlink targets."""
    if not path.name or path.name in {".", ".."}:
        raise ValueError("invalid-output-directory")
    if path.exists() or path.is_symlink():
        raise ValueError("output-directory-already-exists")
    if not path.parent.is_dir() or path.parent.is_symlink():
        raise ValueError("output-parent-must-be-existing-ordinary-directory")
    parts = {p.casefold() for p in path.parts}
    if (".cache" in parts or ".local" in parts or "models" in parts
            or "runtime" in parts or "geniex" in parts):
        raise ValueError("output-must-not-be-in-model-or-service-tree")


def build_onnx_model():
    """Small QDQ-quantized Conv+ReLU: fixed 8x8 input and simple weights."""
    try:
        import onnx
        from onnx import TensorProto, helper
    except ImportError as exc:
        raise RuntimeError("host-onnx-python-package-required") from exc

    tensor = helper.make_tensor
    init = [
        tensor("x_scale", TensorProto.FLOAT, [], [1.0 / 32.0]),
        tensor("x_zero", TensorProto.UINT8, [], [128]),
        tensor("w_i8", TensorProto.INT8, [1, 1, 3, 3],
               [0, 1, 0, 1, 4, 1, 0, 1, 0]),
        tensor("w_scale", TensorProto.FLOAT, [], [1.0 / 64.0]),
        tensor("w_zero", TensorProto.INT8, [], [0]),
        tensor("y_scale", TensorProto.FLOAT, [], [1.0 / 32.0]),
        tensor("y_zero", TensorProto.UINT8, [], [0]),
    ]
    ops = [
        helper.make_node("QuantizeLinear", ["input", "x_scale", "x_zero"],
                         ["x_quant"]),
        helper.make_node("DequantizeLinear", ["x_quant", "x_scale", "x_zero"],
                         ["x_dequant"]),
        helper.make_node("DequantizeLinear", ["w_i8", "w_scale", "w_zero"],
                         ["w_dequant"]),
        helper.make_node("Conv", ["x_dequant", "w_dequant"], ["conv"],
                         pads=[1, 1, 1, 1]),
        helper.make_node("Relu", ["conv"], ["relu"]),
        helper.make_node("QuantizeLinear", ["relu", "y_scale", "y_zero"],
                         ["y_quant"]),
        helper.make_node("DequantizeLinear", ["y_quant", "y_scale", "y_zero"],
                         ["output"]),
    ]
    graph = helper.make_graph(
        ops, MODEL_NAME,
        [helper.make_tensor_value_info("input", TensorProto.FLOAT, INPUT_SHAPE)],
        [helper.make_tensor_value_info("output", TensorProto.FLOAT, INPUT_SHAPE)],
        initializer=init,
    )
    model = helper.make_model(graph, opset_imports=[helper.make_operatorsetid("", 13)],
                              producer_name="MyAI isolated QAIRT microprofile fixture")
    model.ir_version = 8
    onnx.checker.check_model(model)
    return model


def create_host_sample(output_dir: Path, machine: str | None = None) -> dict:
    if is_ventuno_arch(machine or platform.machine()):
        raise RuntimeError("host-only-refuse-arm-target")
    validate_new_output_dir(output_dir)
    # Prepare the validated ONNX graph BEFORE creating files on disk.
    model = build_onnx_model()
    import onnx

    output_dir.mkdir(mode=0o700)
    onnx.save_model(model, str(output_dir / (MODEL_NAME + ".onnx")))
    (output_dir / "input.raw").write_bytes(raw_input_data())
    # This is the ONNX input name. Conversion may rename tensors: verify later.
    (output_dir / "input_list.txt").write_text(
        "input:=input.raw\n", encoding="utf-8"
    )
    evidence = {
        "fixture": MODEL_NAME,
        "onnx_opset": 13,
        "input_shape": list(INPUT_SHAPE),
        "input_dtype": "float32",
        "input_native_bytes": len(raw_input_data()),
        "onnx_graph_checked": True,
        "qnn_converted": False,
        "qnn_context_compatible_with_target": False,
        "input_name_unchanged_by_qnn_converter": False,
        "htp_execution_measured": False,
        "service_changes_allowed": False,
    }
    (output_dir / "fixture_metadata.json").write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return evidence


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    try:
        outcome = create_host_sample(args.output_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        # Only fixed error categories are exposed; never print filesystem paths.
        if isinstance(exc, OSError):
            print("Host fixture creation failed: file-system-error")
        else:
            print("Host fixture creation failed:", str(exc))
        return 2
    print("Host-only ONNX fixture created:", json.dumps(outcome, sort_keys=True))
    print("QNN/HTP conversion and NPU profiling NOT attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
