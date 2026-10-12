"""Inspect exact synthetic QAIRT 2.45 DLC with Qualcomm's own DLC tool.

Host-only, after isolated official converter run. Read-only DLC parse;
does not build or execute HTP contexts. Returns no raw model paths,
tensor names, user data, or unbounded tool output to CI.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import math
import re
import subprocess
import sys
from pathlib import Path

from scripts.qairt_245_host_conversion_trial import (
    SDK_VERSION, sdk_env, sanitized_converter_error,
)

SHA256 = "137ea7f4386d0e7a090bb3d2348432eb7f90da70edf04ea15afc523948dee3ba"
DLC_SIZE = 16004


def summarize_official_io_tables(stdout: str) -> dict[str, object]:
    """Extract dimensions/declared types from Qualcomm's DLC-info tables.

    Fail closed on unknown tool layouts. Never expose tensor names or paths.
    This describes the DLC file, not a QNN backend's native tensor buffers.
    """
    outputs: dict[str, list[dict[str, object]]] = {"input": [], "output": []}
    section: str | None = None
    for raw in stdout[:131072].splitlines():
        line = raw.strip()
        lower = line.lower()
        if "|" in lower and "dimensions" in lower:
            if "input name" in lower:
                section = "input"
                continue
            if "output name" in lower:
                section = "output"
                continue
        if not line.startswith("|") or not line.endswith("|") or section is None:
            continue
        parts = [p.strip() for p in line.strip("|").split("|")]
        if len(parts) < 3 or len(outputs[section]) >= 8:
            continue
        dim_text = parts[1]
        if not re.fullmatch(r"[0-9]+(?:,[0-9]+){0,5}", dim_text):
            continue
        dims = [int(p) for p in dim_text.split(",")]
        if not all(0 < d <= 8192 for d in dims):
            continue
        dtype = parts[2].lower()
        if dtype not in {
            "float_32", "float_16", "float_64", "int_8", "uint_8",
            "int_16", "uint_16", "int_32", "uint_32", "bool_8",
        }:
            continue
        encoding_text = parts[3].lower() if len(parts) >= 4 else ""
        encoding: bool | None = None
        if "no encoding info" in encoding_text or "no encoding" in encoding_text:
            encoding = False
        elif "encoding" in encoding_text or "scale" in encoding_text:
            encoding = True
        outputs[section].append({
            "dimensions": dims,
            "declared_dtype": dtype,
            "elements": math.prod(dims),
            "encoding_declared": encoding,
        })
    inputs = outputs["input"]
    # Exact 256 bytes of float32 as declared in the ONNX source fixture.
    input_matches = (
        len(inputs) == 1 and
        inputs[0]["declared_dtype"] == "float_32" and
        inputs[0]["elements"] == 64
    )
    return {
        "dlc_declared_inputs": inputs,
        "dlc_declared_outputs": outputs["output"],
        "dlc_io_tables_both_parsed": bool(inputs and outputs["output"]),
        "synthetic_float32_input_byte_size_matches_dlc": input_matches,
        "qnn_native_io_compatibility_verified": False,
    }


def inspect_with_qualcomm(sdk: Path, model: Path) -> dict[str, object]:
    info: dict[str, object] = {
        "status": "no-go-unverified-inputs",
        "official_dlc_reader_present": False,
        "dlc_bytes_verified": False,
        "reader_exit_zero": False,
        "reader_output_nonempty": False,
        "reader_structure_claim_proven": False,
        "native_tensor_encoding_verified": False,
        "htp_compatibility_verified": False,
        "htp_execution_verified": False,
        "services_modified": False,
    }
    if platform.machine().lower() not in ("x86_64", "amd64"):
        return info
    if sdk.is_symlink() or not sdk.is_dir() or sdk.name != SDK_VERSION:
        return info
    if model.is_symlink() or not model.is_file() or model.stat().st_size != DLC_SIZE:
        return info
    if hashlib.sha256(model.read_bytes()).hexdigest() != SHA256:
        return info
    info["dlc_bytes_verified"] = True
    tools = sdk / "bin" / "x86_64-linux-clang"
    executable = tools / "qairt-dlc-info"
    if executable.is_symlink() or not executable.is_file():
        info["status"] = "inconclusive-official-dlc-reader-missing"
        return info
    info["official_dlc_reader_present"] = True
    with executable.open("rb") as stream:
        header = stream.read(4)
    argv = ([] if header.startswith(b"\x7fELF") else [sys.executable]) + [
        str(executable), "-i", str(model)
    ]
    try:
        run = subprocess.run(
            argv, env=sdk_env(sdk), cwd=model.parent,
            text=True, errors="replace", capture_output=True,
            timeout=25, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as err:
        info["status"] = "inconclusive-reader-" + type(err).__name__
        return info
    info["reader_exit_zero"] = run.returncode == 0
    stdout = run.stdout[:131072]
    info["reader_output_nonempty"] = bool(stdout.strip())
    # These are *presence of keywords*, not validation of tensor names,
    # Native QNN datatypes, HTP partitioning or actual graph placement.
    lower = stdout.lower()
    info["mentions_input"] = "input" in lower
    info["mentions_output"] = "output" in lower
    info["mentions_layer"] = "layer" in lower
    info.update(summarize_official_io_tables(stdout))
    if run.returncode != 0:
        info["status"] = "inconclusive-official-dlc-reader-error"
        info["error_hint"] = sanitized_converter_error(run.stderr + "\n" + run.stdout)
    elif info["reader_output_nonempty"] and info["mentions_input"] and info["mentions_output"]:
        info["status"] = "official-dlc-reader-parsed-model"
        info["reader_structure_claim_proven"] = True
    else:
        info["status"] = "inconclusive-reader-output"
    return info


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--dlc", type=Path, required=True)
    args = parser.parse_args()
    info = inspect_with_qualcomm(args.sdk_root, args.dlc)
    print("Official Qualcomm DLC semantic inspection:",
          json.dumps(info, sort_keys=True))
    print("Host-side model parsing is NOT HTP validation or inference.")
    return 0 if info["status"] == "official-dlc-reader-parsed-model" else 2


if __name__ == "__main__":
    raise SystemExit(main())
