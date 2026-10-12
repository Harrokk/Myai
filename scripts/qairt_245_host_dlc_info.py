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
import re
import subprocess
import sys
from pathlib import Path

from scripts.qairt_245_host_conversion_trial import (
    SDK_VERSION, sdk_env, sanitized_converter_error,
)

SHA256 = "137ea7f4386d0e7a090bb3d2348432eb7f90da70edf04ea15afc523948dee3ba"
DLC_SIZE = 16004


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
