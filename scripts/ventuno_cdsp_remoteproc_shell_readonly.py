"""Bounded non-invasive remoteproc and CDSP FastRPC shell metadata inventory.

Only fixed sysfs attributes and at most 64 bytes of two allowlisted
FastRPC shell library regular-file headers are read. No DSP device opens,
no kernel logs, no firmware binaries, no QNN/model execution and no
production mutation. Raw names, firmware paths and link targets are omitted.
"""
import json
from pathlib import Path
import re

from scripts.ventuno_v75_elf_fastrpc_readonly import inspect_resolved_skel

REMOTEPROC_ROOT = Path("/sys/class/remoteproc")
SHELLS = {
    "dsp_cdsp": Path("/usr/lib/dsp/cdsp/fastrpc_shell_unsigned_3"),
    "dsp_root": Path("/usr/lib/dsp/fastrpc_shell_unsigned_3"),
}
MAX_REMOTEPROC = 24


def small_attr(path, limit=256):
    """Bounded sysfs read only; never emit original contents."""
    try:
        with path.open("rb") as reader:
            data = reader.read(limit + 1)
        if len(data) > limit:
            return None
        return data.decode("ascii").strip()
    except (OSError, UnicodeError, ValueError):
        return None


def classify_dsp_label(raw):
    if raw is None:
        return "unknown"
    # Enforce token boundaries so substring coincidences are not treated
    # as a distinct Qualcomm DSP. No raw label is ever returned.
    label = raw.lower()
    if re.search(r"(?<![a-z0-9])cdsp(?![a-z0-9])", label):
        return "cdsp"
    if re.search(r"(?<![a-z0-9])adsp(?![a-z0-9])", label):
        return "adsp"
    return "unclassified"


def classify_state(raw):
    return raw.lower() if raw in {"running", "offline", "suspended", "crashed"} else "unknown"


def remoteprocs(root=REMOTEPROC_ROOT):
    summary = {
        "remoteproc_count": 0,
        "cdsp_count": 0,
        "cdsp_state": "unknown",
        "cdsp_firmware_attribute_readable": None,
        "cdsp_firmware_name_looks_like_cdsp": None,
        "count_complete": True,
    }
    try:
        entries = sorted(
            (x for x in root.iterdir() if re.fullmatch(r"remoteproc[0-9]+", x.name)),
            key=lambda x: x.name,
        )
    except OSError:
        summary["count_complete"] = False
        return summary
    if len(entries) > MAX_REMOTEPROC:
        summary["count_complete"] = False
        entries = entries[:MAX_REMOTEPROC]
    summary["remoteproc_count"] = len(entries)
    cdsp_items = []
    for entry in entries:
        if classify_dsp_label(small_attr(entry / "name", 128)) != "cdsp":
            continue
        cdsp_items.append(entry)
    summary["cdsp_count"] = len(cdsp_items)
    if len(cdsp_items) == 1:
        node = cdsp_items[0]
        summary["cdsp_state"] = classify_state(small_attr(node / "state", 64))
        firmware = small_attr(node / "firmware", 256)
        summary["cdsp_firmware_attribute_readable"] = firmware is not None
        if firmware is not None:
            summary["cdsp_firmware_name_looks_like_cdsp"] = (
                classify_dsp_label(firmware) == "cdsp"
            )
    return summary


def shell_headers(paths=SHELLS):
    outcome = {}
    for key, path in paths.items():
        # The shared bounded implementation verifies in-tree regular file,
        # checked file identity and reads <=64 bytes. No library is executed.
        inspected = inspect_resolved_skel(path, Path("/usr"))
        outcome[key] = {
            "resolved_regular_under_usr": (
                inspected["file_regular"] is True
                and inspected["path_inside_usr"] is True
            ),
            "elf_architecture": inspected["header_class"],
            "file_header_read": inspected["library_file_header_read"],
        }
    return outcome


def report():
    return {
        "probe": "ventuno_cdsp_remoteproc_and_shell_readonly",
        "remoteproc": remoteprocs(),
        "unsigned_shells": shell_headers(),
        "firmware_version_or_build_match_proven": False,
        "signed_unsigned_pd_session_verified": False,
        "backend_initialization_verified": False,
        "device_node_opened": False,
        "model_or_npu_run": False,
        "production_modified": False,
        "raw_firmware_paths_or_shell_links_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_CDSP_SHELL_READONLY_JSON=" + json.dumps(report(), sort_keys=True))
