"""Bounded standalone QAIRT 2.45 host ONNX-to-DLC/QNN conversion trial.

DO NOT deploy to a device. This only creates small temporary *synthetic*
model artifacts on an isolated x86 GitHub-hosted machine after verifying the
Qualcomm archive and ONNX SHA-256. It is intentionally not a VENTUNO workflow.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
from pathlib import Path

from scripts.qairt_host_toolchain_preflight import verified_fixture_presence

MAX_OUTPUT_BYTES = 20 * 1024 * 1024
TIME_LIMIT_SECONDS = 110
SDK_VERSION = "2.45.0.260326"


def command_for_tool(tool: Path, input_file: Path, output_file: Path) -> list[str]:
    if tool.name not in ("qairt-converter", "qnn-onnx-converter"):
        raise ValueError("not-an-allowlisted-converter")
    if tool.is_symlink() or not tool.is_file():
        raise ValueError("converter-missing-or-symlink")
    if not input_file.is_file() or input_file.is_symlink():
        raise ValueError("unverified-source-input")
    if output_file.exists() or output_file.is_symlink():
        raise ValueError("refuse-existing-output")
    with tool.open("rb") as stream:
        header = stream.read(4)
    prefix = [] if header.startswith(b"\x7fELF") else [sys.executable]
    return prefix + [str(tool), "--input_network", str(input_file),
                     "--output_path", str(output_file)]


def sanitized_missing_dependency(text: str) -> str | None:
    found = re.search(
        r"ModuleNotFoundError: No module named ['\"]([A-Za-z_][A-Za-z0-9_.]{0,63})['\"]",
        text,
    )
    return found.group(1) if found else None


def sanitized_converter_error(text: str) -> str | None:
    """Small diagnostic fragment for synthetic-only ephemeral host executions.

    Mask absolute POSIX paths, credentials and long tokens; never emit raw
    process environment or original arbitrary converter stdout/stderr.
    """
    lines = [line.strip() for line in text[-5000:].splitlines() if line.strip()]
    if not lines:
        return None
    candidates = [line for line in lines if
                  any(term in line.lower() for term in (
                      "error", "failed", "exception", "no module", "traceback",
                      "usage:", "missing", "not found", "invalid", "unsupported",
                  ))]
    chosen = candidates[-2:] if candidates else lines[-1:]
    output = []
    for line in chosen:
        line = re.sub(r"/[^\\s:,;\\]\[\]\\(\\)\\{\\}]+", "<path>", line)
        line = re.sub(r"(?i)(bearer|api[_-]?key|token|password)\\s*[:=]\\s*\\S+",
                      "<redacted>", line)
        line = re.sub(r"(?<![A-Za-z0-9])[A-Za-z0-9+/]{65,}={0,2}", "<long-value>", line)
        output.append(line[:200])
    return " | ".join(output)[:420]


def sdk_env(root: Path) -> dict[str, str]:
    lib = root / "lib" / "x86_64-linux-clang"
    env = os.environ.copy()
    env["QAIRT_SDK_ROOT"] = str(root)
    env["QNN_SDK_ROOT"] = str(root)
    env["PYTHONPATH"] = os.pathsep.join(
        [str(root / "lib" / "python"), str(root / "bin" / "x86_64-linux-clang"),
         env.get("PYTHONPATH", "")]
    )
    env["LD_LIBRARY_PATH"] = os.pathsep.join(
        [str(lib), env.get("LD_LIBRARY_PATH", "")]
    )
    return env


def run_one(tool: Path, source: Path, output: Path, env: dict) -> dict[str, object]:
    result: dict[str, object] = {
        "tool": tool.name,
        "status": "not-attempted",
        "missing_python_dependency": None,
        "output_created": False,
        "output_size_bytes": 0,
        "output_sha256": None,
        "qnn_context_generated": False,
        "htp_profiling_measured": False,
    }
    if not tool.is_file() or tool.is_symlink():
        result["status"] = "tool-not-present"
        return result
    try:
        argv = command_for_tool(tool, source, output)
    except (OSError, ValueError):
        result["status"] = "rejected-unsafe-conversion-arguments"
        return result
    # Use timeout and capped log capture, never print model/cache filesystem paths
    try:
        run = subprocess.run(
            argv, cwd=output.parent, env=env, timeout=TIME_LIMIT_SECONDS,
            capture_output=True, text=True, errors="replace", check=False,
        )
        result["return_code_zero"] = run.returncode == 0
        result["exit_code"] = run.returncode
        result["error_hint"] = sanitized_converter_error(
            run.stderr + "\\n" + run.stdout
        ) if run.returncode else None
        result["missing_python_dependency"] = sanitized_missing_dependency(
            (run.stderr + "\n" + run.stdout)[-4096:]
        )
        if run.returncode:
            result["status"] = "converter-exited-nonzero"
            return result
        if not output.is_file() or output.is_symlink():
            result["status"] = "converter-output-missing"
            return result
        size = output.stat().st_size
        if not 0 < size <= MAX_OUTPUT_BYTES:
            result["status"] = "converter-output-oversize-or-empty"
            return result
        result["output_created"] = True
        result["output_size_bytes"] = size
        result["output_sha256"] = hashlib.sha256(output.read_bytes()).hexdigest()
        result["status"] = "host-source-conversion-success"
    except subprocess.TimeoutExpired:
        result["status"] = "converter-timeout"
    except OSError:
        result["status"] = "converter-file-error"
    return result


def conversion_trial(sdk: Path, fixture: Path, destination: Path) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "no-go",
        "host_architecture_verified": platform.machine().lower() in ("x86_64", "amd64"),
        "source_onnx_checksum_verified": False,
        "sdk_version_path_verified": False,
        "results": [],
        "qnn_htp_context_built": False,
        "qnn_native_inputs_verified": False,
        "npu_profiling_verified": False,
        "production_services_changed": False,
    }
    if not report["host_architecture_verified"]:
        return report
    if (not sdk.is_dir() or sdk.is_symlink()
            or sdk.name != SDK_VERSION):
        report["status"] = "reject-unexpected-sdk-location"
        return report
    report["sdk_version_path_verified"] = True
    verified = verified_fixture_presence(fixture)
    report["source_onnx_checksum_verified"] = verified
    if not verified:
        report["status"] = "reject-model-checksum"
        return report
    if destination.exists() or destination.is_symlink() or not destination.parent.is_dir():
        report["status"] = "reject-output-directory"
        return report
    # Output is strictly isolated from SDK, model cache and source fixture.
    if sdk in destination.parents or fixture in destination.parents:
        report["status"] = "reject-output-under-input-or-sdk"
        return report
    destination.mkdir(mode=0o700)
    tools = sdk / "bin" / "x86_64-linux-clang"
    env = sdk_env(sdk)
    source = fixture / "tiny_qdq_conv.onnx"
    results = [
        run_one(tools / "qairt-converter", source,
                destination / "tiny_qdq_conv.dlc", env),
        run_one(tools / "qnn-onnx-converter", source,
                destination / "tiny_qdq_conv.cpp", env),
    ]
    report["results"] = results
    if any(r.get("output_created") for r in results):
        report["status"] = "host-converter-produced-unverified-model-format"
    else:
        report["status"] = "host-conversion-inconclusive"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    report = conversion_trial(args.sdk_root, args.fixture_dir, args.output_dir)
    print("QAIRT 2.45 isolated host conversion trial:", json.dumps(report, sort_keys=True))
    return 0 if report["status"] == "host-converter-produced-unverified-model-format" else 2


if __name__ == "__main__":
    raise SystemExit(main())
