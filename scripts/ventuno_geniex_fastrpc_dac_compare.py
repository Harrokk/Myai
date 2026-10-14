"""Compare read-only DAC permission bits for runtime vs active GenieX PIDs.

No device files are opened. No UID, GID, group ID, PID, device name,
process path, or service argument is emitted to the GitHub log.
POSIX mode checks are only approximations; ACL/MAC/capabilities may differ.
"""

import json
import os
from pathlib import Path
import re
import stat

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, service_tree, is_geniex_process,
)


def _ids_from_status(path):
    try:
        lines = path.read_text(encoding="ascii", errors="replace")[:16000].splitlines()
    except OSError:
        return None
    fields = {}
    for line in lines:
        if line.startswith(("Uid:", "Gid:", "Groups:")):
            key, raw = line.split(":", 1)
            if not re.fullmatch(r"\s*[0-9]+(?:\s+[0-9]+)*\s*", raw):
                return None
            fields[key] = [int(x) for x in raw.split()]
    uid = fields.get("Uid")
    gid = fields.get("Gid")
    groups = fields.get("Groups", [])
    if uid is None or gid is None or len(uid) != 4 or len(gid) != 4:
        return None
    return {"fsuid": uid[3], "fsgid": gid[3], "groups": frozenset(groups)}


def dac_mode_permits(mode, owner, group, fsuid, fsgid, supp_groups):
    """Compute only classic POSIX DAC mode; root/caps/ACL not represented."""
    if fsuid == owner:
        return {
            "read": bool(mode & stat.S_IRUSR),
            "write": bool(mode & stat.S_IWUSR),
        }
    if group == fsgid or group in supp_groups:
        return {
            "read": bool(mode & stat.S_IRGRP),
            "write": bool(mode & stat.S_IWGRP),
        }
    return {
        "read": bool(mode & stat.S_IROTH),
        "write": bool(mode & stat.S_IWOTH),
    }


def summarize():
    secure = Path("/dev/fastrpc-cdsp-secure")
    result = {
        "probe": "live_geniex_vs_runner_fastrpc_dac_metadata",
        "secure_rpc_character_device_present": False,
        "runner_mode_read": False,
        "runner_mode_write": False,
        "geniex_matching_processes": 0,
        "geniex_status_readable_count": 0,
        "geniex_any_process_mode_write": False,
        "geniex_all_checked_processes_mode_write": False,
        "geniex_different_fsuid_from_runner": None,
        "geniex_any_root_fsuid": False,
        "effective_kernel_open_access_tested": False,
        "acl_or_mac_policy_checked": False,
        "runtime_cred_capabilities_checked": False,
        "device_opened": False,
        "service_modified": False,
    }
    try:
        st = secure.lstat()
    except OSError:
        return result
    if not stat.S_ISCHR(st.st_mode):
        return result
    result["secure_rpc_character_device_present"] = True
    mode = stat.S_IMODE(st.st_mode)
    runner = dac_mode_permits(
        mode, st.st_uid, st.st_gid,
        os.geteuid(), os.getegid(), frozenset(os.getgroups()),
    )
    result["runner_mode_read"] = runner["read"]
    result["runner_mode_write"] = runner["write"]

    pid = main_pid_from_systemd()
    if pid is None:
        return result
    proc = Path("/proc")
    matching = [
        p for p in service_tree(proc, pid)
        if is_geniex_process(proc, p)
    ]
    result["geniex_matching_processes"] = len(matching)
    decisions = []
    differences = []
    for process_id in matching:
        ids = _ids_from_status(proc / str(process_id) / "status")
        if ids is None:
            continue
        result["geniex_status_readable_count"] += 1
        differences.append(ids["fsuid"] != os.geteuid())
        result["geniex_any_root_fsuid"] |= ids["fsuid"] == 0
        decision = dac_mode_permits(
            mode, st.st_uid, st.st_gid,
            ids["fsuid"], ids["fsgid"], ids["groups"],
        )
        decisions.append(decision)
    result["geniex_any_process_mode_write"] = any(x["write"] for x in decisions)
    result["geniex_all_checked_processes_mode_write"] = bool(decisions) and all(
        x["write"] for x in decisions
    )
    result["geniex_different_fsuid_from_runner"] = (
        any(differences) if differences else None
    )
    return result


if __name__ == "__main__":
    print("MYAI_GENIEX_FASTRPC_DAC_COMPARISON_JSON=" +
          json.dumps(summarize(), sort_keys=True))
