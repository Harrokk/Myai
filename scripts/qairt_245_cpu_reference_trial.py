"""Compare an isolated x86 QAIRT CPU DLC run with an independent ONNX oracle.

Only a 16,004-byte synthetic DLC, its 64-byte UFXP8 input and QAIRT 2.45
CPU backend are allowed. Refuses ARM/Ventuno, live GenieX and unverified
artifacts. Produces a bounded pass/fail report without exposing private paths.
No HTP context, DSP or NPU profiling is attempted.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import platform
import subprocess
from pathlib import Path

from scripts.prepare_qairt245_native_fixture import (
    OUTPUT_SCALE, OUTPUT_QNN_OFFSET, MODEL_SHA, native_input,
)
from scripts.qairt_245_host_conversion_trial import SDK_VERSION, sdk_env
from scripts.qairt_host_toolchain_preflight import verified_fixture_presence

EXPECTED_DLC_BYTES = 16004
MAX_RUN_SECONDS = 50
MAX_OUTPUT_BYTES = 16 * 1024


def verify_dlc(path: Path) -> bool:
    if not path.is_file() or path.is_symlink():
        return False
    try:
        if path.stat().st_size != EXPECTED_DLC_BYTES:
            return False
        return hashlib.sha256(path.read_bytes()).hexdigest() == MODEL_SHA
    except OSError:
        return False


def verify_native_file(path: Path) -> bool:
    try:
        return (
            not path.is_symlink() and path.is_file()
            and path.stat().st_size == 64
            and path.read_bytes() == native_input()
        )
    except OSError:
        return False


def cpu_cli_arguments(sdk: Path, dlc: Path, input_list: Path, output: Path) -> list[str]:
    tools = sdk / "bin" / "x86_64-linux-clang"
    libs = sdk / "lib" / "x86_64-linux-clang"
    return [
        str(tools / "qnn-net-run"),
        "--backend", str(libs / "libQnnCpu.so"),
        "--model", str(libs / "libQnnModelDlc.so"),
        "--dlc_path", str(dlc),
        "--input_list", str(input_list),
        "--output_dir", str(output),
        "--use_native_input_files",
        "--use_native_output_files",
    ]


def bounded_output_files(folder: Path) -> list[Path]:
    """Only Result_0 output, no traversal, symlinks or unbounded globbing."""
    if folder.is_symlink() or not folder.is_dir():
        return []
    result = folder / "Result_0"
    if result.is_symlink() or not result.is_dir():
        return []
    candidates = []
    for index, entry in enumerate(result.iterdir()):
        if index >= 12:
            return []
        if entry.is_symlink() or not entry.is_file():
            continue
        if entry.suffix.lower() != ".raw":
            continue
        if not 0 < entry.stat().st_size <= MAX_OUTPUT_BYTES:
            return []
        candidates.append(entry)
    return candidates


def oracle_reference(onnx_path: Path, input_float32: Path):
    import numpy as np
    import onnxruntime as ort
    if onnx_path.is_symlink() or not onnx_path.is_file():
        raise ValueError("unverified-onnx-path")
    source = np.frombuffer(input_float32.read_bytes(), dtype="<f4").reshape(1, 1, 8, 8)
    session = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    if session.get_providers() != ["CPUExecutionProvider"]:
        raise RuntimeError("unexpected-non-cpu-provider")
    return session.run(None, {"input": source})[0].reshape(-1)


def compare_native_outputs(raw: bytes, expected: object) -> dict[str, object]:
    """Decode QNN UFXP8 and match ONNX within 1.5 native quantization steps."""
    import numpy as np
    if len(raw) != 64 or len(expected) != 64:
        return {"status": "reject-output-size", "matches": False}
    q = np.frombuffer(raw, dtype=np.uint8)
    decoded = (q.astype(np.float32) + OUTPUT_QNN_OFFSET) * OUTPUT_SCALE
    reference = np.asarray(expected, dtype=np.float32).reshape(-1)
    if not np.isfinite(reference).all():
        return {"status": "reject-nonfinite-oracle", "matches": False}
    max_abs_error = float(np.max(np.abs(decoded - reference)))
    all_close = bool(np.all(np.abs(decoded - reference) <= 1.5 * OUTPUT_SCALE + 1e-6))
    nonzero = int(np.count_nonzero(q))
    return {
        "status": "cpu-matches-onnx-reference" if all_close and nonzero
                  else "cpu-output-differs-from-onnx",
        "matches": all_close and nonzero > 0,
        "max_abs_error": round(max_abs_error, 8),
        "nonzero_output_values": nonzero,
        "output_raw_sha256": hashlib.sha256(raw).hexdigest(),
        "comparison_tolerance": 1.5 * OUTPUT_SCALE + 1e-6,
        "htp_execution_verified": False,
    }


def trial(sdk: Path, dlc: Path, original_fixture: Path,
          native_dir: Path, output: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "no-go",
        "source_verified": False,
        "dlc_verified": False,
        "native_input_verified": False,
        "cpu_backend_loaded": False,
        "cpu_reference_matched": False,
        "htp_context_built": False,
        "htp_executed": False,
        "ventuno_services_modified": False,
    }
    if platform.machine().lower() not in {"x86_64", "amd64"}:
        return report
    if sdk.is_symlink() or sdk.name != SDK_VERSION or not sdk.is_dir():
        report["status"] = "reject-sdk-version"
        return report
    if not verified_fixture_presence(original_fixture):
        report["status"] = "reject-original-onnx"
        return report
    report["source_verified"] = True
    if not verify_dlc(dlc):
        report["status"] = "reject-dlc-digest"
        return report
    report["dlc_verified"] = True
    native_file = native_dir / "input_native_u8.raw"
    if (native_dir.is_symlink() or not native_dir.is_dir()
            or not verify_native_file(native_file)
            or (native_dir / "input_list_native.txt").is_symlink()
            or not (native_dir / "input_list_native.txt").is_file()
            or (native_dir / "input_list_native.txt").read_text(encoding="utf-8")
               != "input_native_u8.raw\n"):
        report["status"] = "reject-native-input-list"
        return report
    report["native_input_verified"] = True
    tool = sdk / "bin" / "x86_64-linux-clang" / "qnn-net-run"
    libs = sdk / "lib" / "x86_64-linux-clang"
    if any(p.is_symlink() or not p.is_file() for p in (
        tool, libs / "libQnnCpu.so", libs / "libQnnModelDlc.so",
    )):
        report["status"] = "no-go-cpu-sdk-tools-missing"
        return report
    if output.exists() or output.is_symlink() or not output.parent.is_dir():
        report["status"] = "reject-output-path"
        return report
    if sdk in output.parents or original_fixture in output.parents or native_dir in output.parents:
        report["status"] = "reject-output-under-model-or-sdk"
        return report

    env = sdk_env(sdk)
    env["QNN_LOG_LEVEL"] = "ERROR"
    try:
        result = subprocess.run(
            cpu_cli_arguments(sdk, dlc, native_dir / "input_list_native.txt", output),
            cwd=native_dir, env=env, capture_output=True, text=True,
            errors="replace", timeout=MAX_RUN_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        report["status"] = "cpu-net-run-timeout"
        return report
    except OSError as error:
        report["status"] = "cpu-net-run-launch-error"
        report["launch_errno"] = getattr(error, "errno", None)
        report["runner_executable_permission"] = os.access(tool, os.X_OK)
        return report
    report["exit_code_zero"] = result.returncode == 0
    if result.returncode != 0:
        report["status"] = "cpu-net-run-nonzero"
        return report
    report["cpu_backend_loaded"] = True
    outputs = bounded_output_files(output)
    report["native_output_files_found"] = len(outputs)
    if len(outputs) != 1 or outputs[0].stat().st_size != 64:
        report["status"] = "cpu-native-output-missing-or-ambiguous"
        return report
    try:
        expected = oracle_reference(
            original_fixture / "tiny_qdq_conv.onnx",
            original_fixture / "input.raw",
        )
        comparison = compare_native_outputs(outputs[0].read_bytes(), expected)
    except (OSError, ValueError, RuntimeError, ImportError):
        report["status"] = "cpu-oracle-error"
        return report
    report["comparison"] = comparison
    report["cpu_reference_matched"] = bool(comparison["matches"])
    report["status"] = comparison["status"]
    return report


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", required=True, type=Path)
    parser.add_argument("--dlc", required=True, type=Path)
    parser.add_argument("--fixture-dir", required=True, type=Path)
    parser.add_argument("--native-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    result = trial(args.sdk_root, args.dlc, args.fixture_dir,
                   args.native_dir, args.output_dir)
    print("Isolated QAIRT CPU parity:", json.dumps(result, sort_keys=True))
    print("CPU host only; HTP/NPU and production GenieX untouched.")
    return 0 if result["cpu_reference_matched"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
