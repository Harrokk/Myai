"""Read-only go/no-go for tiny synthetic QNN HTP candidate on real VENTUNO.

Never calls qnn-net-run with a model, creates contexts, loads contexts, alters
GenieX, accesses USB/audio or executes NPU inference. Only inspect installed
tool/SDK presence and the immutable 16,004-byte synthetic fixture digest.
"""

import json
import shutil
from pathlib import Path

from scripts.qairt_245_dlc_static_audit import DEFAULT_FIXTURE, verify_fixture
from scripts.ventuno_qnn_cli_gate import inspect_installed_cli
from scripts.ventuno_qnn_microprofile_inventory import (
    installed_tools, candidate_inventory, readiness_report,
)


LIBRARIES = (
    "libQnnModelDlc.so",
    "libQnnHtp.so",
    "libQnnHtpV75Stub.so",
    "libQnnCpu.so",
)
ROOTS = (
    Path("/usr/lib"),
    Path("/usr/local/lib"),
    Path("/usr/lib/aarch64-linux-gnu"),
    Path("/opt/qcom"),
    Path("/opt/qualcomm"),
    Path("/opt/qairt"),
    Path("/home/arduino/.local/share/geniex/qairt"),
)


def library_presence(roots=ROOTS):
    """Bounded symlink-free scan of allowlisted SDK roots, names never printed."""
    found = {name: False for name in LIBRARIES}
    visited = set()
    budget = 320
    queue = [(p, 0) for p in roots if p.is_dir() and not p.is_symlink()]
    while queue and budget > 0:
        directory, depth = queue.pop(0)
        try:
            identity = directory.stat()
            key = (identity.st_dev, identity.st_ino)
            if key in visited:
                continue
            visited.add(key)
            entries = list(directory.iterdir())[:100]
        except OSError:
            continue
        budget -= 1
        for entry in entries:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file() and entry.name in found:
                    found[entry.name] = True
                elif entry.is_dir() and depth < 5 and budget > 0:
                    queue.append((entry, depth + 1))
            except OSError:
                continue
    return found, {"directories_visited": len(visited),
                   "scan_exhausted_budget": bool(queue)}


def main():
    verified = verify_fixture(DEFAULT_FIXTURE)
    inventory = candidate_inventory(ROOTS)
    tools = installed_tools()
    htp_libs, budget = library_presence()
    qnn_cli = inspect_installed_cli()
    tiny_verified = verified.get("file_identity_verified") is True
    model_dlc = htp_libs.get("libQnnModelDlc.so", False)
    htp = htp_libs.get("libQnnHtp.so", False)
    # Additional model operator validation/context input tensor I/O is still
    # required even if all these prerequisite indicators are true.
    status = (
        "candidate_prerequisites_present_but_unproven"
        if tiny_verified and model_dlc and htp and tools.get("qnn-net-run")
        else "no_go_independent_compatible_context_not_yet_verified"
    )
    result = {
        "probe": "real_ventuno_tiny_qnn_htp_preflight",
        "status": status,
        "verified_synthetic_tiny_dlc_16004_bytes": tiny_verified,
        "verified_native_input_shape": "UFXP8_1x1x8x8_64_bytes",
        "installed_tools": tools,
        "allowlisted_library_presence": htp_libs,
        "scan_budget": budget,
        "qnn_cli_graph_selector_status": qnn_cli.get("status"),
        "qnn_cli_graph_selectors": qnn_cli.get("graph_selectors", []),
        "sdk_example_candidate_status": readiness_report(tools, inventory)["status"],
        "qnn_context_compatible_proven": False,
        "qnn_htp_operator_placement_proven": False,
        "model_inference_executed": False,
        "second_large_model_started": False,
        "production_geniex_modified": False,
        "hardware_permission_changed": False,
    }
    print("MYAI_TINY_QNN_HTP_READINESS_JSON=" + json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
