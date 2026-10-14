"""Read-only ELF/SDK follow-up to instant tiny-QNN HTP startup rejection.

No model inference, no subprocess of QNN tools, no driver operations.
Outputs booleans and counts only, never library paths or environment values.
"""

import json
import os
from pathlib import Path

from scripts.ventuno_tiny_qnn_htp_once import _find_libraries
from scripts.ventuno_tiny_qnn_htp_readiness import ROOTS


def is_aarch64_elf(path):
    try:
        with path.open("rb") as stream:
            header = stream.read(64)
    except OSError:
        return False
    if len(header) < 20 or header[:4] != b"\x7fELF":
        return False
    # ELFCLASS64=2; little endian=1; EM_AARCH64=183 (0x00b7).
    return header[4] == 2 and header[5] == 1 and header[18:20] == b"\xb7\x00"


def count_skels():
    roots = (
        Path("/usr/lib/rfsa/adsp"),
        Path("/vendor/dsp"),
        Path("/opt/qcom"),
        Path("/opt/qualcomm"),
        Path("/home/arduino/.local/share/geniex/qairt"),
    )
    names = {"libQnnHtpV75Skel.so", "libQnnHtpV75Stub.so"}
    found = {name: False for name in names}
    queue = [(r, 0) for r in roots if r.is_dir() and not r.is_symlink()]
    count = 0
    while queue and count < 320:
        folder, depth = queue.pop(0)
        count += 1
        try:
            items = list(folder.iterdir())[:120]
        except OSError:
            continue
        for entry in items:
            try:
                if entry.is_symlink():
                    continue
                if entry.is_file() and entry.name in names:
                    found[entry.name] = True
                elif entry.is_dir() and depth < 5:
                    queue.append((entry, depth + 1))
            except OSError:
                continue
    return found, bool(queue)


def report():
    libraries = _find_libraries()
    skels, capped = count_skels()
    evidence = {
        "probe": "read_only_tiny_htp_startup_compatibility",
        "library_found": {name: name in libraries for name in (
            "libQnnHtp.so", "libQnnModelDlc.so", "libQnnHtpV75Stub.so",
        )},
        "library_is_aarch64_elf": {
            name: is_aarch64_elf(libraries[name]) if name in libraries else False
            for name in ("libQnnHtp.so", "libQnnModelDlc.so", "libQnnHtpV75Stub.so")
        },
        "hexagon_v75_skeleton_present_in_sampled_locations": skels["libQnnHtpV75Skel.so"],
        "hexagon_v75_stub_present_in_sampled_locations": skels["libQnnHtpV75Stub.so"],
        "skeleton_scan_capped": capped,
        "adsp_library_path_configured_in_runner": bool(os.environ.get("ADSP_LIBRARY_PATH")),
        "ld_library_path_configured_in_runner": bool(os.environ.get("LD_LIBRARY_PATH")),
        "previous_exit_0_039s_root_cause_proven": False,
        "htp_executed": False,
        "model_loaded": False,
        "live_services_modified": False,
    }
    return evidence


if __name__ == "__main__":
    print("MYAI_TINY_QNN_HTP_ELF_DIAGNOSTIC_JSON=" +
          json.dumps(report(), sort_keys=True))
