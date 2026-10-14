"""Classify CDSP firmware search metadata without firmware-file reads.

Linux firmware search-path presence is only an indicator; firmware can load
from initramfs or vendor-specific fallback. No /dev opens, firmware bytes,
symlink target, raw sysfs firmware name, logs or user identifiers exported.
"""
import json
import os
from pathlib import Path
import re
import stat

from scripts.ventuno_cdsp_remoteproc_shell_readonly import (
    REMOTEPROC_ROOT, MAX_REMOTEPROC, small_attr, classify_dsp_label,
    classify_state,
)

FIRMWARE_ROOT = Path("/lib/firmware")
CUSTOM_SEARCH_PARAMETER = Path("/sys/module/firmware_class/parameters/path")
SAFE_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,63}$")
MAX_FIRMWARE_NAME = 192


def verified_firmware_name(raw):
    """Accept relative components only; reject path traversal and secrets."""
    if not raw or len(raw) > MAX_FIRMWARE_NAME:
        return None
    if any(ord(ch) < 33 or ord(ch) > 126 for ch in raw):
        return None
    components = raw.split("/")
    if any(
        component in ("", ".", "..") or not SAFE_COMPONENT.fullmatch(component)
        for component in components
    ):
        return None
    return components


def cdsp_entry(root=REMOTEPROC_ROOT):
    """Identify one CDSP using same name/DT predicates as prior validated probe."""
    try:
        entries = sorted(
            (p for p in root.iterdir()
             if re.fullmatch(r"remoteproc[0-9]+", p.name)),
            key=lambda p: p.name,
        )
    except OSError:
        return "unavailable", None
    if len(entries) > MAX_REMOTEPROC:
        return "over_budget", None
    matches = []
    for entry in entries:
        raw_name = small_attr(entry / "name", 128)
        raw_dt = small_attr(entry / "device" / "of_node" / "compatible", 256)
        if "cdsp" in {
            classify_dsp_label(raw_name),
            classify_dsp_label(raw_dt),
        }:
            matches.append(entry)
    if len(matches) != 1:
        return ("ambiguous" if matches else "not_identified"), None
    if classify_state(small_attr(matches[0] / "state", 64)) != "running":
        return "not_running", None
    return "one_running_cdsp", matches[0]


def candidate_metadata(segments, root=FIRMWARE_ROOT, release=None):
    """Only lstat/resolve exact kernel firmware filesystem search candidates."""
    try:
        real_root = root.resolve(strict=True)
        if not real_root.is_dir():
            return {"search_roots_available": False, "checked": 0,
                    "existing_regular_files": 0, "out_of_tree_links": 0}
    except (OSError, RuntimeError):
        return {"search_roots_available": False, "checked": 0,
                "existing_regular_files": 0, "out_of_tree_links": 0}
    if release is None:
        release = os.uname().release
    if not SAFE_COMPONENT.fullmatch(release):
        release = None
    prefixes = [("updates",), ()]
    if release is not None:
        prefixes = [("updates", release), ("updates",), (release,), ()]
    result = {"search_roots_available": True, "checked": 0,
              "existing_regular_files": 0, "out_of_tree_links": 0}
    for parts in prefixes:
        candidate = root.joinpath(*parts, *segments)
        result["checked"] += 1
        try:
            # Do not open the binary; symlinks are resolved solely as metadata.
            if not candidate.exists() and not candidate.is_symlink():
                continue
            resolved = candidate.resolve(strict=True)
            if not resolved.is_relative_to(real_root):
                result["out_of_tree_links"] += 1
                continue
            if stat.S_ISREG(resolved.lstat().st_mode):
                result["existing_regular_files"] += 1
        except (OSError, RuntimeError):
            continue
    return result


def custom_path_indicator(path=CUSTOM_SEARCH_PARAMETER):
    raw = small_attr(path, 256)
    if raw is None:
        return "unavailable"
    return "configured" if bool(raw) else "empty"


def report(remoteproc_root=REMOTEPROC_ROOT, firmware_root=FIRMWARE_ROOT,
           custom_path=CUSTOM_SEARCH_PARAMETER):
    classification, node = cdsp_entry(remoteproc_root)
    result = {
        "probe": "ventuno_cdsp_firmware_search_path_metadata_only",
        "cdsp_identity": classification,
        "cdsp_running": classification == "one_running_cdsp",
        "sysfs_firmware_name_validated": False,
        "firmware_filesystem_search": "not_checked",
        "candidate_metadata": None,
        "firmware_custom_search_parameter": custom_path_indicator(custom_path),
        "initramfs_firmware_presence_verified": False,
        "actual_firmware_image_running_identity_proven": False,
        "firmware_shell_build_compatibility_proven": False,
        "no_firmware_contents_read": True,
        "no_dsp_or_qnn_execution": True,
        "no_device_node_opened": True,
        "no_production_changes": True,
        "no_raw_firmware_names_or_paths_exported": True,
    }
    if node is None:
        return result
    raw = small_attr(node / "firmware", MAX_FIRMWARE_NAME)
    name = verified_firmware_name(raw)
    if name is None:
        result["firmware_filesystem_search"] = "invalid_or_unavailable_name"
        return result
    result["sysfs_firmware_name_validated"] = True
    result["candidate_metadata"] = candidate_metadata(name, firmware_root)
    result["firmware_filesystem_search"] = (
        "regular_candidate_found"
        if result["candidate_metadata"]["existing_regular_files"] > 0 else
        "no_regular_candidate_in_sampled_paths"
        if result["candidate_metadata"]["search_roots_available"] else
        "search_root_unavailable"
    )
    return result


if __name__ == "__main__":
    print("MYAI_CDSP_FIRMWARE_SEARCH_JSON=" +
          json.dumps(report(), sort_keys=True))
