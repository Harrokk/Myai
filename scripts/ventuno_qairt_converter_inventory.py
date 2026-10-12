"""Read-only QAIRT 2.45 conversion toolchain evidence on VENTUNO Q.

This probe checks only public SDK tool file names and --help/--version on
already installed binaries. It never opens context/model files, runs
converters with a model, elevates privileges, downloads SDKs or touches
production GenieX. A command absent from PATH may exist elsewhere.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections import deque
from pathlib import Path

TOOL_NAMES = (
    "qnn-onnx-converter", "qnn-model-lib-generator",
    "qnn-context-binary-generator", "qnn-net-run", "qnn-profile-viewer",
    "snpe-onnx-to-dlc", "qairt-converter",
)
TARGET_FILE_NAMES = frozenset(
    list(TOOL_NAMES) + ["qnn-onnx-converter.py", "qnn-model-lib-generator.py"]
)
SDK_LIB_NAMES = frozenset(
    ("libQnnHtp.so", "libQnnHtpV75Stub.so",
     "libQnnHtpV75Skel.so", "libQnnSystem.so")
)
MAX_DIRS = 120
MAX_FILES = 1000
MAX_DEPTH = 5
MAX_ENTRIES = 280


def sdk_file_inventory(roots: tuple[Path, ...]) -> dict[str, object]:
    pending = deque((p, 0) for p in roots if p.is_dir() and not p.is_symlink())
    roots_present = len(pending)
    inspected_dirs = inspected_files = 0
    capped = unreadable = False
    seen_tools: set[str] = set()
    seen_libs: set[str] = set()
    while pending and inspected_dirs < MAX_DIRS and inspected_files < MAX_FILES:
        folder, depth = pending.popleft()
        inspected_dirs += 1
        try:
            with os.scandir(folder) as scan:
                entries = []
                for index, entry in enumerate(scan):
                    if index >= MAX_ENTRIES:
                        capped = True
                        break
                    entries.append(entry)
        except OSError:
            unreadable = True
            continue
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    if depth < MAX_DEPTH:
                        pending.append((Path(entry.path), depth + 1))
                    else:
                        capped = True
                    continue
                if not entry.is_file(follow_symlinks=False):
                    continue
                inspected_files += 1
                if inspected_files >= MAX_FILES:
                    capped = True
                    break
                if entry.name in TARGET_FILE_NAMES:
                    seen_tools.add(entry.name)
                if entry.name in SDK_LIB_NAMES:
                    seen_libs.add(entry.name)
            except OSError:
                unreadable = True
    if pending or inspected_dirs >= MAX_DIRS:
        capped = True
    return {
        "sdk_roots_present": roots_present,
        "directories_checked": inspected_dirs,
        "files_checked": inspected_files,
        "scan_capped": capped,
        "unreadable": unreadable,
        "tool_names_present_beyond_or_within_path": sorted(seen_tools),
        "sdk_library_names_present": sorted(seen_libs),
        "production_model_files_inspected": False,
    }


def relevant_cli_options(text: str) -> dict[str, bool]:
    flags = set(re.findall(r"(?<!\w)--[a-z][a-z0-9_-]{1,40}\b", text.lower()))
    return {flag: flag in flags for flag in (
        "--dlc_path", "--model", "--retrieve_context",
        "--backend", "--binary_file", "--config_file",
        "--profiling_level", "--profiling_option",
    )}


def command_evidence(tool: str) -> dict[str, object]:
    if tool not in TOOL_NAMES:
        raise ValueError("unapproved-tool")
    path = shutil.which(tool)
    if not path:
        return {"path_available": False, "help_readable": False}
    report: dict[str, object] = {"path_available": True, "help_readable": False}
    try:
        result = subprocess.run(
            [path, "--help"], capture_output=True, text=True, errors="replace",
            timeout=7, check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        report["error_type"] = type(exc).__name__
        return report
    # Print only recognized flags, not SDK paths, raw --help or environment.
    if result.returncode == 0:
        report["help_readable"] = True
        report["flags"] = relevant_cli_options(
            (result.stdout + "\n" + result.stderr)[:250000]
        )
    else:
        report["help_exit_nonzero"] = True
    return report


def decision(evidence: dict[str, dict], inventory: dict) -> dict[str, object]:
    convert = evidence.get("qnn-onnx-converter", {}).get("path_available", False)
    model_lib = evidence.get("qnn-model-lib-generator", {}).get(
        "path_available", False
    )
    context = evidence.get("qnn-context-binary-generator", {})
    dlc_flag = context.get("flags", {}).get("--dlc_path", False)
    tools_on_disk = set(inventory.get("tool_names_present_beyond_or_within_path", []))
    if (inventory.get("scan_capped") or inventory.get("unreadable")):
        status = "inconclusive-bounded-scan"
    elif convert and model_lib:
        status = "candidate-host-toolchain-check-version-and-abi"
    elif {"qnn-onnx-converter", "qnn-model-lib-generator"} <= tools_on_disk:
        status = "candidate-offpath-tools-not-validated"
    elif dlc_flag:
        status = "dlc-loading-option-present-but-dlc-creation-unverified"
    else:
        status = "no-go-converter-or-valid-standalone-dlc-missing"
    return {
        "status": status,
        "context_generator_dlc_input_flag_present": dlc_flag,
        "complete_conversion_chain_verified": False,
        "qairt_245_abi_compatibility_verified": False,
        "valid_independent_dlc_or_qnn_model_available": False,
        "safe_to_start_htp_profile": False,
        "safe_to_modify_running_services": False,
    }


def main() -> int:
    home = Path.home()
    roots = (
        home / ".local" / "share" / "geniex" / "qairt",
        home / ".local" / "share" / "qairt",
        home / ".local" / "bin",
        Path("/opt/qairt"), Path("/opt/qcom"), Path("/opt/qualcomm"),
        Path("/usr/local/qairt"),
    )
    print("QAIRT conversion chain compatibility inventory (read-only)")
    inventory = sdk_file_inventory(roots)
    print("Known SDK tool names:", json.dumps(inventory, sort_keys=True))
    # Invocations are allowlisted --help only. No converter used on a model.
    observed = {name: command_evidence(name) for name in (
        "qnn-onnx-converter", "qnn-model-lib-generator",
        "qnn-context-binary-generator", "qnn-net-run",
    )}
    print("Tool help evidence:", json.dumps(observed, sort_keys=True))
    print("Conversion readiness:", json.dumps(
        decision(observed, inventory), sort_keys=True
    ))
    print("No model loaded, context generated, profiling started, or service changed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
