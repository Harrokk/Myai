"""Read-only host SDK preflight for tiny ONNX -> QNN conversion.

Run explicitly on a development host with an *authorized* installed QAIRT
SDK, never on VENTUNO. Does not load SDK dynamic libraries, import Qualcomm
Python packages, invoke conversion, print private paths, download packages,
write files or mark the context runnable. Detects known tool file locations
only. A verified SDK version, ABI and native tensor data remain separate gates.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path

from scripts.prepare_tiny_qnn_host_sample import is_ventuno_arch

EXPECTED_SHA256 = "e347c2197d3006e32eec580c85a6eb2c0cbd460150d4a72ae80e9d78573b94f9"
EXPECTED_MODEL_SIZE = 608
CONVERTER_NAMES = ("qnn-onnx-converter", "qnn-onnx-converter.py",
                   "qnn-onnx-converter.exe")
LIB_GENERATOR_NAMES = ("qnn-model-lib-generator",
                       "qnn-model-lib-generator.py",
                       "qnn-model-lib-generator.exe")


def inspect_files(dir: Path, names: tuple[str, ...]) -> bool:
    if not dir.is_dir() or dir.is_symlink():
        return False
    for name in names:
        candidate = dir / name
        try:
            if candidate.is_file() and not candidate.is_symlink():
                return True
        except OSError:
            pass
    return False


def sdk_tool_status(sdk_root: Path, host: str) -> dict[str, object]:
    host_tag = {
        "linux": "x86_64-linux-clang",
        "windows": "x86_64-windows-msvc",
    }.get(host)
    if host_tag is None:
        raise ValueError("unsupported-development-host")
    if not sdk_root.is_dir() or sdk_root.is_symlink():
        return {"sdk_root_present": False, "host": host,
                "converter_found": False, "model_lib_generator_found": False}
    tool_root = sdk_root / "bin" / host_tag
    # Some Windows QAIRT SDKs place the model-library generator in an
    # aarch64-windows-msvc directory, even though the converter is under
    # x86_64-windows-msvc. Presence is NOT proof of execution/ABI support.
    model_lib_dirs = [tool_root]
    if host == "windows":
        model_lib_dirs.append(sdk_root / "bin" / "aarch64-windows-msvc")
    return {
        "sdk_root_present": True,
        "host": host,
        "converter_found": inspect_files(tool_root, CONVERTER_NAMES),
        "model_lib_generator_found": any(
            inspect_files(directory, LIB_GENERATOR_NAMES)
            for directory in model_lib_dirs
        ),
    }


def verified_fixture_presence(folder: Path) -> bool:
    if not folder.is_dir() or folder.is_symlink():
        return False
    model_file = folder / "tiny_qdq_conv.onnx"
    if model_file.is_symlink() or not model_file.is_file():
        return False
    try:
        if model_file.stat().st_size != EXPECTED_MODEL_SIZE:
            return False
        return hashlib.sha256(model_file.read_bytes()).hexdigest() == EXPECTED_SHA256
    except OSError:
        return False


def readiness(sdk: dict[str, object], verified_source: bool) -> dict[str, object]:
    converted = bool(sdk.get("converter_found")) and bool(
        sdk.get("model_lib_generator_found")
    )
    if not sdk.get("sdk_root_present"):
        status = "sdk-not-supplied"
    elif not verified_source:
        status = "no-go-onnx-artifact-identity-unverified"
    elif not converted:
        status = "no-go-host-converter-chain-incomplete"
    else:
        status = "candidate-tools-present-manual-qairt-version-and-abi-review"
    return {
        "status": status,
        "host_converter_tools_present": converted,
        "source_model_sha256_matches_verified_build": verified_source,
        "qairt_sdk_version_245_verified": False,
        "required_target_abi_and_htp_backend_verified": False,
        "converter_model_support_verified": False,
        "onnx_to_qnn_conversion_completed": False,
        "htp_context_created": False,
        "npu_profiling_authorized": False,
        "myai_geniex_services_changed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sdk-root", type=Path, required=True)
    parser.add_argument("--fixture-dir", type=Path, required=True)
    parser.add_argument("--host", choices=("linux", "windows"), required=True)
    args = parser.parse_args()
    if is_ventuno_arch(platform.machine()):
        print("Refusing QAIRT host SDK preflight on ARM target")
        return 2
    sdk = sdk_tool_status(args.sdk_root, args.host)
    check = verified_fixture_presence(args.fixture_dir)
    print("QAIRT host SDK preflight (read-only)")
    print("SDK tool availability:", json.dumps(sdk, sort_keys=True))
    print("Converter readiness:", json.dumps(readiness(sdk, check), sort_keys=True))
    print("No converter executed; SDK version and target ABI unverified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
