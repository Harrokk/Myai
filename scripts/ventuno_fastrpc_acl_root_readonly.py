"""Read-only ACL/capability indicators and udev root aliases on real VENTUNO.

Only emits allowlisted booleans/enums: no IDs, paths, kernel labels, ACL
payloads, process commands, environment, personal data or raw udev rules.
Never opens FastRPC/DMA device nodes, executes QNN or mutates services.
"""
import errno
import json
import os
from pathlib import Path
import re
import stat

from scripts.ventuno_fastrpc_policy_readonly import (
    DEVICE_NAMES, metadata_for_device, fastrpc_gid, one_geniex_identity,
)
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, service_tree, is_geniex_process,
)

RULE_ROOTS = {
    "etc": Path("/etc/udev/rules.d"),
    "usr_lib": Path("/usr/lib/udev/rules.d"),
    "lib": Path("/lib/udev/rules.d"),
}
MAX_STATUS_BYTES = 16384


def classify_rule_roots(roots=RULE_ROOTS):
    """Report root type and only whether lib is an alias of usr_lib."""
    observed = {}
    stats = {}
    for label, path in roots.items():
        try:
            st = path.lstat()
        except FileNotFoundError:
            observed[label] = "missing"
            continue
        except OSError:
            observed[label] = "unreadable"
            continue
        if stat.S_ISLNK(st.st_mode):
            observed[label] = "symlink"
        elif stat.S_ISDIR(st.st_mode):
            observed[label] = "directory"
        else:
            observed[label] = "other"
        if observed[label] in ("directory", "symlink"):
            try:
                stats[label] = path.stat()  # metadata only; never reads targets
            except OSError:
                pass
    vendor = stats.get("usr_lib")
    alternate = stats.get("lib")
    alias = (
        (vendor.st_dev, vendor.st_ino) == (alternate.st_dev, alternate.st_ino)
        if vendor is not None and alternate is not None else None
    )
    return {"root_types": observed, "lib_aliases_usr_lib": alias}


def acl_indicator(path):
    """Read but NEVER export ACL xattr bytes from an exact character node."""
    try:
        st = path.lstat()
    except OSError:
        return "device_absent_or_inaccessible"
    if not stat.S_ISCHR(st.st_mode):
        return "not_character_device"
    try:
        # Metadata read only: no open/read of the device itself.
        value = os.getxattr(path, "system.posix_acl_access", follow_symlinks=False)
        return "acl_present" if value else "acl_empty"
    except OSError as exc:
        no_data = {errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)}
        not_supported = {errno.ENOTSUP, errno.EOPNOTSUPP}
        if exc.errno in no_data:
            return "not_exposed"
        if exc.errno in not_supported:
            return "unsupported"
        return "unavailable"
    except (TypeError, NotImplementedError):
        return "unavailable"


def effective_capabilities_indicator(status_path):
    """Boolean only; do not return or log the CapEff value."""
    try:
        with status_path.open("rb") as stream:
            payload = stream.read(MAX_STATUS_BYTES + 1)
    except OSError:
        return None
    if len(payload) > MAX_STATUS_BYTES:
        return None
    matches = re.findall(rb"(?m)^CapEff:\s*([0-9a-fA-F]{1,16})\s*$", payload)
    if len(matches) != 1:
        return None
    return int(matches[0], 16) != 0


def geniex_effective_caps(proc_root=Path("/proc")):
    pid = main_pid_from_systemd()
    if pid is None:
        return None
    matching = [
        p for p in service_tree(proc_root, pid)
        if is_geniex_process(proc_root, p)
    ]
    if len(matching) != 1:
        return None
    return effective_capabilities_indicator(proc_root / str(matching[0]) / "status")


def report(dev_root=Path("/dev"), rule_roots=RULE_ROOTS):
    group = fastrpc_gid()
    geniex = one_geniex_identity()
    dma_path = dev_root / DEVICE_NAMES["dma_heap_system"]
    dma = metadata_for_device(dma_path, group, geniex)
    classic = dma["runner_has_classic_dac_write"]
    effective = dma["runner_effective_write_access"]
    return {
        "probe": "ventuno_fastrpc_acl_and_root_alias_readonly",
        "udev_root_structure": classify_rule_roots(rule_roots),
        "runner_effective_capabilities_nonzero":
            effective_capabilities_indicator(Path("/proc/self/status")),
        "geniex_effective_capabilities_nonzero": geniex_effective_caps(),
        "dma_heap_acl_indicator": acl_indicator(dma_path),
        "secure_cdsp_acl_indicator":
            acl_indicator(dev_root / DEVICE_NAMES["cdsp_secure"]),
        "dma_heap_runner_write_effective_but_classic_dac_denied":
            effective is True and classic is False
            if effective is not None and classic is not None else None,
        "dma_heap_geniex_classic_dac_write": dma["geniex_has_classic_dac_write"],
        "acl_payload_exported": False,
        "device_open_attempted": False,
        "production_modified": False,
        "qnn_or_htp_attempted": False,
        "interpretation": "metadata_only_no_open_or_backend_proof",
    }


if __name__ == "__main__":
    print("MYAI_FASTRPC_ACL_ROOT_JSON=" + json.dumps(report(), sort_keys=True))
