"""Host-only numerical verification of a tiny QAIRT ONNX source fixture.

Executes only ONNX Runtime's CPU execution provider on a separate host, never
QNN, GenieX, model binaries, or HTP. Validates an independent NumPy oracle,
rounding, actual nonzero outputs, byte sizes and strict input model schema.

This confirms ONNX math, not compatibility with QAIRT 2.45 or HTP placement.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

from scripts.prepare_tiny_qnn_host_sample import (
    INPUT_COUNT, INPUT_SHAPE, MODEL_NAME, is_ventuno_arch,
    raw_input_data,
)

MAX_MODEL_BYTES = 1024 * 1024


def verify_fixture(folder: Path, *, machine: str | None = None) -> dict[str, object]:
    if is_ventuno_arch(machine or platform.machine()):
        raise RuntimeError("host-only-refuse-arm-target")
    if not folder.is_dir() or folder.is_symlink():
        raise ValueError("invalid-fixture-directory")
    model_file = folder / (MODEL_NAME + ".onnx")
    input_file = folder / "input.raw"
    input_list = folder / "input_list.txt"
    metadata_file = folder / "fixture_metadata.json"
    for path, size_limit in (
        (model_file, MAX_MODEL_BYTES),
        (input_file, 256),
        (input_list, 128),
        (metadata_file, 4096),
    ):
        if (path.is_symlink() or not path.is_file()
                or not 0 < path.stat().st_size <= size_limit):
            raise ValueError("incomplete-or-oversize-fixture")
    if input_file.read_bytes() != raw_input_data():
        raise ValueError("fixture-input-mismatch")
    if input_list.read_text(encoding="utf-8") != "input:=input.raw\n":
        raise ValueError("fixture-input-list-mismatch")
    evidence = json.loads(metadata_file.read_text(encoding="utf-8"))
    if (not isinstance(evidence, dict)
            or evidence.get("onnx_graph_checked") is not True
            or evidence.get("qnn_converted") is not False
            or evidence.get("htp_execution_measured") is not False):
        raise ValueError("fixture-metadata-inconsistent")

    try:
        import numpy as np
        import onnx
        import onnxruntime as ort
    except ImportError as exc:
        raise RuntimeError("host-onnx-onnxruntime-numpy-packages-required") from exc

    model = onnx.load(str(model_file))
    onnx.checker.check_model(model, full_check=True)
    opset = next((o.version for o in model.opset_import if o.domain == ""), None)
    if (model.ir_version != 8 or opset != 13
            or len(model.graph.node) != 7
            or [n.op_type for n in model.graph.node] != [
                "QuantizeLinear", "DequantizeLinear", "DequantizeLinear",
                "Conv", "Relu", "QuantizeLinear", "DequantizeLinear",
            ]):
        raise ValueError("unexpected-onnx-graph")

    x = np.frombuffer(input_file.read_bytes(), dtype="<f4").reshape(INPUT_SHAPE)
    session = ort.InferenceSession(
        str(model_file), providers=["CPUExecutionProvider"]
    )
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise RuntimeError("unexpected-runtime-provider")
    result = session.run(None, {"input": x})[0]
    assert result.shape == INPUT_SHAPE, "invalid-reference-output-shape"
    assert result.dtype == np.float32, "invalid-reference-output-dtype"
    assert np.isfinite(result).all(), "nonfinite-reference-output"

    # Independent float32 oracle for this fixed graph's Q/DQ/Conv/ReLU/Q/DQ.
    xq = np.rint(x / np.float32(1 / 32) + 128).clip(0, 255).astype(np.uint8)
    xd = (xq.astype(np.float32) - 128) * np.float32(1 / 32)
    weights = np.array([[0, 1, 0], [1, 4, 1], [0, 1, 0]], dtype=np.float32)
    weights *= np.float32(1 / 64)
    padded = np.pad(xd[0, 0], ((1, 1), (1, 1)))
    conv = np.empty((8, 8), dtype=np.float32)
    for row in range(8):
        for col in range(8):
            conv[row, col] = np.sum(
                padded[row:row+3, col:col+3] * weights,
                dtype=np.float32,
            )
    positive = np.maximum(conv, 0)
    yscale = np.float32(1 / 512)
    yquant = np.rint(positive / yscale).clip(0, 255).astype(np.uint8)
    expected = (yquant.astype(np.float32) * yscale).reshape(INPUT_SHAPE)
    np.testing.assert_allclose(result, expected, atol=1e-7, rtol=0)
    active_outputs = int(np.count_nonzero(result))
    if active_outputs == 0 or active_outputs == INPUT_COUNT:
        raise ValueError("noninformative-output")

    raw_result = result.astype("<f4", copy=False).tobytes()
    if len(raw_result) != INPUT_COUNT * 4:
        raise ValueError("invalid-reference-output-bytes")

    return {
        "onnx_checker_passed": True,
        "onnxruntime_cpu_executed": True,
        "independent_numpy_oracle_matched": True,
        "output_tensor_shape": list(result.shape),
        "nonzero_output_elements": active_outputs,
        "reference_output_sha256": hashlib.sha256(raw_result).hexdigest(),
        "onnx_sha256": hashlib.sha256(model_file.read_bytes()).hexdigest(),
        "native_input_bytes": INPUT_COUNT * 4,
        "qnn_conversion_verified": False,
        "htp_profile_measured": False,
        "production_services_modified": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = verify_fixture(args.fixture_dir)
    except (ValueError, OSError, RuntimeError, AssertionError) as exc:
        if isinstance(exc, (OSError, AssertionError)):
            reason = type(exc).__name__
        else:
            # Errors originating in dependencies can include paths. Sanitize.
            allowed = {
                "host-only-refuse-arm-target", "invalid-fixture-directory",
                "incomplete-or-oversize-fixture", "fixture-input-mismatch",
                "fixture-input-list-mismatch", "fixture-metadata-inconsistent",
                "host-onnx-onnxruntime-numpy-packages-required",
                "unexpected-runtime-provider", "unexpected-onnx-graph",
                "noninformative-output", "invalid-reference-output-bytes",
            }
            reason = str(exc) if str(exc) in allowed else type(exc).__name__
        print("Host ONNX verification inconclusive:", reason)
        return 2
    print("Host ONNX verification:", json.dumps(report, sort_keys=True))
    print("ONNX Runtime CPU-only math verified; QNN conversion and NPU execution NOT attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
