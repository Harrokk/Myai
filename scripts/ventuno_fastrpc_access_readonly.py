"""Read-only FastRPC access prerequisites on real VENTUNO, no device open.

Queries only metadata for /dev/fastrpc* and /dev/adsprpc*, effective UID
DAC access plus trusted OS security status. Never prints UID, GID, path,
MAC, token, process details, capabilities or arbitrary command output.
No NPU, GenieX, audio or system service is accessed or changed.
"""
import json
import os
from pathlib import Path
import shutil
import stat


def rpc_category(name):
    name = name.lower()
    if not name.startswith(("fastrpc", "adsprpc")):
        return None
    if "cdsp" in name and name.endswith("-secure"):
        return "cdsp_secure"
    if "cdsp" in name:
        return "cdsp_nonsecure"
    return "other_rpc_nodes"


def classify_rpc_nodes(dev_root=Path("/dev")):
    groups = {
        "cdsp_secure": {"exists": False, "character_device": False, "effective_read": False,
                        "effective_write": False},
        "cdsp_nonsecure": {"exists": False, "character_device": False, "effective_read": False,
                          "effective_write": False},
        "other_rpc_nodes": {"count": 0},
    }
    for node in sorted(dev_root.glob("*rpc*"))[:40]:
        name = node.name.lower()
        key = rpc_category(name)
        if key is None:
            continue
        try:
            info = node.lstat()
            if not stat.S_ISCHR(info.st_mode):
                continue
        except OSError:
            continue
        if key == "other_rpc_nodes":
            groups[key]["count"] += 1
            continue
        groups[key]["exists"] = True
        groups[key]["character_device"] = True
        groups[key]["effective_read"] = (
            groups[key]["effective_read"] or os.access(node, os.R_OK, effective_ids=True)
        )
        groups[key]["effective_write"] = (
            groups[key]["effective_write"] or os.access(node, os.W_OK, effective_ids=True)
        )
    return groups


def runtime_security_indicators():
    # No security labels, process details or user IDs are disclosed.
    def value(path):
        try:
            return Path(path).read_text(encoding="ascii", errors="ignore").strip()
        except OSError:
            return ""
    return {
        "selinux_enforce_flag": value("/sys/fs/selinux/enforce") == "1",
        "apparmor_enabled_flag": value("/sys/module/apparmor/parameters/enabled") == "Y",
        "qnn_platform_validator_on_path": shutil.which("qnn-platform-validator") is not None,
        "qnn_net_run_on_path": shutil.which("qnn-net-run") is not None,
    }


def report():
    rpc = classify_rpc_nodes()
    secure = rpc["cdsp_secure"]
    return {
        "probe": "real_ventuno_rpc_access_metadata_only",
        "rpc_nodes": rpc,
        "security_indicators": runtime_security_indicators(),
        "secure_cdsp_open_ability_verified": False,
        "secure_cdsp_metadata_access_suggests_possible_permission_block":
            secure["exists"] and (not secure["effective_read"] or not secure["effective_write"]),
        "htp_model_loaded": False,
        "device_open_attempted": False,
        "inference_attempted": False,
        "production_modified": False,
    }


if __name__ == "__main__":
    print("MYAI_FASTRPC_ACCESS_METADATA_JSON=" + json.dumps(report(), sort_keys=True))
