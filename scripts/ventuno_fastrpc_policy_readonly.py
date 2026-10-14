"""Bounded, metadata-only FastRPC vendor-policy inspection on VENTUNO.

Reads /etc/group via NSS for *only* the fastrpc GID, current process groups,
a single systemd-identified GenieX's /proc/status IDs, stat/access metadata
for three fixed char-device nodes, and bounded udev rule *text* (no logs).
Never opens a /dev device, sends an RPC, invokes QNN, changes permissions,
prints user/group IDs, prints paths or reads service environment/content.
"""
import grp
import json
import os
from pathlib import Path
import re
import stat

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, service_tree, is_geniex_process,
)
from scripts.ventuno_geniex_fastrpc_dac_compare import (
    _ids_from_status, dac_mode_permits,
)

DEVICE_NAMES = {
    "cdsp_secure": "fastrpc-cdsp-secure",
    "cdsp_nonsecure": "fastrpc-cdsp",
    "dma_heap_system": "dma_heap/system",
}
RULE_DIRS = (
    Path("/etc/udev/rules.d"),
    Path("/usr/lib/udev/rules.d"),
    Path("/lib/udev/rules.d"),
)
MAX_RULE_ENTRIES = 256
MAX_RULE_BYTES = 16384


def fastrpc_gid():
    """Only use the resolved gid internally; no usernames or gids are logged."""
    try:
        return grp.getgrnam("fastrpc").gr_gid
    except (KeyError, OSError):
        return None


def one_geniex_identity():
    """Require exactly one positively identified descendant, else unknown."""
    pid = main_pid_from_systemd()
    if pid is None:
        return None
    proc = Path("/proc")
    matches = [p for p in service_tree(proc, pid) if is_geniex_process(proc, p)]
    return _ids_from_status(proc / str(matches[0]) / "status") if len(matches) == 1 else None


def metadata_for_device(path, vendor_gid, geniex):
    result = {
        "character_device": False,
        "device_group_is_fastrpc": None,
        "runner_has_classic_dac_read": None,
        "runner_has_classic_dac_write": None,
        "runner_effective_read_access": None,
        "runner_effective_write_access": None,
        "geniex_has_classic_dac_read": None,
        "geniex_has_classic_dac_write": None,
    }
    try:
        metadata = path.lstat()
    except OSError:
        return result
    if not stat.S_ISCHR(metadata.st_mode):
        return result  # No symlink, block or regular file is trusted as a node.
    result["character_device"] = True
    result["device_group_is_fastrpc"] = (
        metadata.st_gid == vendor_gid if vendor_gid is not None else None
    )
    mode = stat.S_IMODE(metadata.st_mode)
    runner = dac_mode_permits(
        mode, metadata.st_uid, metadata.st_gid,
        os.geteuid(), os.getegid(), frozenset(os.getgroups()),
    )
    result["runner_has_classic_dac_read"] = runner["read"]
    result["runner_has_classic_dac_write"] = runner["write"]
    for kind, flag in (("read", os.R_OK), ("write", os.W_OK)):
        try:
            result[f"runner_effective_{kind}_access"] = os.access(
                path, flag, effective_ids=True
            )
        except (OSError, NotImplementedError, TypeError, ValueError):
            pass
    if geniex is not None:
        checked = dac_mode_permits(
            mode, metadata.st_uid, metadata.st_gid,
            geniex["fsuid"], geniex["fsgid"], geniex["groups"],
        )
        result["geniex_has_classic_dac_read"] = checked["read"]
        result["geniex_has_classic_dac_write"] = checked["write"]
    return result


def bounded_rules_inventory(roots=RULE_DIRS):
    """Read only small, non-symlink regular .rules files; export counts/flags."""
    result = {
        "scanned_rule_files": 0,
        "fastrpc_mention_files": 0,
        "dma_heap_mention_files": 0,
        "fastrpc_group_assignment_seen": False,
        "mode_0640_assignment_seen": False,
        "scan_complete": True,
    }
    visited_dirs = set()
    entries_seen = 0
    if not hasattr(os, "O_NOFOLLOW"):
        result["scan_complete"] = False
        return result
    for root in roots:
        try:
            st = root.lstat()
            if not stat.S_ISDIR(st.st_mode):
                # Never follow rule-root symlinks; disclose that coverage is partial.
                result["scan_complete"] = False
                continue
            identity = (st.st_dev, st.st_ino)
            if identity in visited_dirs:
                continue
            visited_dirs.add(identity)
            with os.scandir(root) as iterator:
                entries = sorted(
                    (entry.path, entry.name) for entry in iterator
                    if entry.name.endswith(".rules")
                )
        except FileNotFoundError:
            continue
        except OSError:
            result["scan_complete"] = False
            continue
        for filename, _ in entries:
            entries_seen += 1
            if entries_seen > MAX_RULE_ENTRIES:
                result["scan_complete"] = False
                return result
            fd = None
            try:
                fd = os.open(
                    filename, os.O_RDONLY | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0)
                )
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_RULE_BYTES:
                    result["scan_complete"] = False
                    continue
                data = os.read(fd, MAX_RULE_BYTES + 1)
                if len(data) > MAX_RULE_BYTES:
                    result["scan_complete"] = False
                    continue
            except OSError:
                result["scan_complete"] = False
                continue
            finally:
                if fd is not None:
                    os.close(fd)
            result["scanned_rule_files"] += 1
            data = data.lower()
            if b"fastrpc" in data:
                result["fastrpc_mention_files"] += 1
            if b"dma_heap" in data:
                result["dma_heap_mention_files"] += 1
            if re.search(rb'\bgroup\s*={1,2}\s*"fastrpc"', data):
                result["fastrpc_group_assignment_seen"] = True
            if re.search(rb'\bmode\s*={1,2}\s*"0640"', data):
                result["mode_0640_assignment_seen"] = True
    return result


def report(dev_root=Path("/dev"), rule_roots=RULE_DIRS):
    group = fastrpc_gid()
    geniex = one_geniex_identity()
    return {
        "probe": "ventuno_fastrpc_vendor_policy_metadata_only",
        "fastrpc_group_exists": group is not None,
        "runner_in_fastrpc_group": (
            group in {os.getegid(), *os.getgroups()} if group is not None else None
        ),
        "one_geniex_identity_readable": geniex is not None,
        "geniex_in_fastrpc_group": (
            group in {geniex["fsgid"], *geniex["groups"]}
            if group is not None and geniex is not None else None
        ),
        "nodes": {
            key: metadata_for_device(dev_root / name, group, geniex)
            for key, name in DEVICE_NAMES.items()
        },
        "udev_policy": bounded_rules_inventory(rule_roots),
        "actual_device_open_verified": False,
        "acl_or_apparmor_enforcement_verified": False,
        "qnn_htp_backend_attempted": False,
        "node_or_service_modified": False,
        "interpretation": "inconclusive_vendor_process_domain_policy_required",
    }


if __name__ == "__main__":
    print("MYAI_FASTRPC_POLICY_METADATA_JSON=" + json.dumps(report(), sort_keys=True))
