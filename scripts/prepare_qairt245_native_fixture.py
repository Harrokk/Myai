"""Build *synthetic* 64-byte QNN DLC-native input on a separate x86 host.

Derived from the official QAIRT 2.45 DLC-info reading for tiny_qdq_conv:
1x1x8x8 UFXP_8; scale 0.03125; QNN offset -128.
QNN QnnTypes.h: real=(quantized+offset)*scale.
No inference, QNN context creation, device transfer, model compilation or
service interruption. The single-input list still requires runtime validation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import struct
from pathlib import Path

from scripts.prepare_tiny_qnn_host_sample import (
    MODEL_NAME, INPUT_COUNT, input_values, is_ventuno_arch,
    validate_new_output_dir,
)
from scripts.qairt_host_toolchain_preflight import verified_fixture_presence
from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture

QUANT_SCALE = 0.03125
QNN_OFFSET = -128
OUTPUT_SCALE = 0.001953125
OUTPUT_QNN_OFFSET = 0
MODEL_SHA = "137ea7f4386d0e7a090bb3d2348432eb7f90da70edf04ea15afc523948dee3ba"
READER_RUN = "https://github.com/Harrokk/Myai/actions/runs/38228157205"


def encode_ufxp8(value: float, *, scale: float = QUANT_SCALE,
                 offset: int = QNN_OFFSET) -> int:
    """Nearest-even quantization; no wraparound for out-of-range values."""
    if (not math.isfinite(value) or not math.isfinite(scale) or scale <= 0
            or type(offset) is not int):
        raise ValueError("invalid-quantization-parameters")
    return max(0, min(255, round(value / scale - offset)))


def decode_ufxp8(value: int, *, scale: float = QUANT_SCALE,
                 offset: int = QNN_OFFSET) -> float:
    if (type(value) is not int or not 0 <= value <= 255
            or not math.isfinite(scale) or scale <= 0
            or type(offset) is not int):
        raise ValueError("invalid-quantized-value")
    return (value + offset) * scale


def native_input() -> bytes:
    source = input_values()
    if len(source) != INPUT_COUNT:
        raise RuntimeError("unexpected-synthetic-source-shape")
    raw = bytes(encode_ufxp8(x) for x in source)
    if len(raw) != 64:
        raise RuntimeError("unexpected-native-quantized-byte-count")
    if any(abs(decode_ufxp8(q) - x) > 1e-7 for q, x in zip(raw, source)):
        raise RuntimeError("quantization-round-trip-not-exact")
    return raw


def produce_native_fixture(
    source_folder: Path, output_folder: Path, *,
    machine: str | None = None,
) -> dict[str, object]:
    if is_ventuno_arch(machine or platform.machine()):
        raise RuntimeError("host-only-refuse-arm-target")
    if not verified_fixture_presence(source_folder):
        raise ValueError("unverified-host-onnx")
    dlc = verify_fixture(DEFAULT_FIXTURE)
    if (not dlc.get("file_identity_verified") or
            dlc.get("dlc_sha256") != MODEL_SHA):
        raise ValueError("unverified-synthetic-dlc")
    validate_new_output_dir(output_folder)
    raw = native_input()
    report = {
        "input_shape": [1, 1, 8, 8],
        "input_dtype": "ufxp_8",
        "input_scale": QUANT_SCALE,
        "input_qnn_offset": QNN_OFFSET,
        "output_dtype": "ufxp_8",
        "output_scale": OUTPUT_SCALE,
        "output_qnn_offset": OUTPUT_QNN_OFFSET,
        "native_input_bytes": len(raw),
        "native_input_sha256": hashlib.sha256(raw).hexdigest(),
        "exact_float32_roundtrip_verified": True,
        "dlc_identity_verified": True,
        "dlc_source": READER_RUN,
        "input_tensor_name_revalidated_by_backend": False,
        "qnn_cpu_result_matched": False,
        "htp_context_created": False,
        "htp_execution_measured": False,
        "live_services_changed": False,
    }
    output_folder.mkdir(mode=0o700)
    (output_folder / "input_native_u8.raw").write_bytes(raw)
    # Single graph input. Relative path resolves to the runner's cwd.
    (output_folder / "input_list_native.txt").write_text(
        "input_native_u8.raw\n", encoding="utf-8",
    )
    (output_folder / "native_fixture_metadata.json").write_text(
        json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8",
    )
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = produce_native_fixture(args.fixture_dir, args.output_dir)
    except (ValueError, OSError, RuntimeError) as exc:
        allowed = {
            "host-only-refuse-arm-target", "unverified-host-onnx",
            "unverified-synthetic-dlc", "invalid-output-directory",
            "output-directory-already-exists",
            "output-parent-must-be-existing-ordinary-directory",
            "output-must-not-be-in-model-or-service-tree",
        }
        msg = str(exc) if str(exc) in allowed else type(exc).__name__
        print("Host native fixture not generated:", msg)
        return 2
    print("Synthetic UFXP_8 input prepared:", json.dumps(report, sort_keys=True))
    print("64-byte native input validated mathematically; QNN execution NOT attempted.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
