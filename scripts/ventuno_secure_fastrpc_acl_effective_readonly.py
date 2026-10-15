"""Read-only effective POSIX ACL diagnosis for VENTUNO secure CDSP FastRPC.

Never opens or writes the device node, reads model/memory/service content,
adjusts permissions or invokes DSP/QNN. Exposes only bounded status labels
and booleans; ACL payloads and numeric identities remain process-private.

An os.access() result is NOT proof of FastRPC-open authorization: vendor
process-domain and backend initialization remain independent requirements.
"""
from __future__ import annotations

import errno
import json
import os
from pathlib import Path
import stat

from scripts.ventuno_dma_acl_effective_readonly import (
    acl_permission, parse_acl,
)
from scripts.ventuno_geniex_fastrpc_dac_compare import dac_mode_permits


TARGET = Path("/dev/fastrpc-cdsp-secure")


def _same_inode(before, after):
    return (
        stat.S_ISCHR(after.st_mode)
        and (before.st_dev, before.st_ino) == (after.st_dev, after.st_ino)
    )


def diagnose(target=TARGET):
    result = {
        "probe": "ventuno_secure_cdsp_fastrpc_acl_effective_readonly",
        "status": "no_go",
        "character_device_verified": False,
        "acl_state": "unverified",
        "classic_mode_runner_read": None,
        "classic_mode_runner_write": None,
        "posix_effective_runner_read": None,
        "posix_effective_runner_write": None,
        "effective_access_runner_read": None,
        "effective_access_runner_write": None,
        "posix_effective_matches_os_access": None,
        "write_denial_classification": "unattributed",
        "device_opened": False,
        "device_written": False,
        "acl_or_identity_exported": False,
        "raw_device_paths_exported": False,
        "service_or_permissions_modified": False,
        "qnn_or_htp_executed": False,
        "npu_inference_verified": False,
    }
    try:
        before = target.lstat()
    except OSError:
        result["status"] = "device_unavailable"
        return result
    if not stat.S_ISCHR(before.st_mode):
        result["status"] = "reject_non_character_device"
        return result

    result["character_device_verified"] = True
    identity = (
        os.geteuid(), os.getegid(), frozenset(os.getgroups())
    )
    classical = dac_mode_permits(
        stat.S_IMODE(before.st_mode), before.st_uid, before.st_gid,
        *identity,
    )
    result["classic_mode_runner_read"] = classical["read"]
    result["classic_mode_runner_write"] = classical["write"]

    posix = None
    try:
        data = os.getxattr(
            target, "system.posix_acl_access", follow_symlinks=False
        )
    except OSError as exc:
        if exc.errno in {
            errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)
        }:
            result["acl_state"] = "no_extended_posix_acl"
            posix = classical
        elif exc.errno in {errno.ENOTSUP, errno.EOPNOTSUPP}:
            result["acl_state"] = "posix_acl_unsupported"
        else:
            result["acl_state"] = "acl_metadata_unavailable"
    except (TypeError, NotImplementedError):
        result["acl_state"] = "acl_metadata_unavailable"
    else:
        parsed = parse_acl(data)
        if parsed is None:
            result["acl_state"] = "acl_format_unrecognized"
        else:
            result["acl_state"] = "posix_acl_v2_parsed"
            posix = acl_permission(
                parsed, before.st_uid, before.st_gid, *identity
            )

    try:
        read = os.access(target, os.R_OK, effective_ids=True)
        write = os.access(target, os.W_OK, effective_ids=True)
        after = target.lstat()
    except (OSError, ValueError, TypeError, NotImplementedError):
        result["status"] = "access_metadata_unavailable"
        return result
    if not _same_inode(before, after):
        # Device replaced between metadata calls; do not report a valid
        # rights comparison from two different filesystem objects.
        result["status"] = "device_identity_changed"
        result["character_device_verified"] = False
        return result

    result["effective_access_runner_read"] = read
    result["effective_access_runner_write"] = write
    if posix is not None:
        result["posix_effective_runner_read"] = posix["read"]
        result["posix_effective_runner_write"] = posix["write"]
        result["posix_effective_matches_os_access"] = (
            posix["read"] is read and posix["write"] is write
        )

    if write is False:
        if result["acl_state"] == "posix_acl_v2_parsed" and posix["write"] is False:
            result["write_denial_classification"] = "posix_acl_write_denied"
        elif result["acl_state"] == "no_extended_posix_acl" and classical["write"] is False:
            result["write_denial_classification"] = "classic_mode_write_denied"
        elif posix is not None and posix["write"] is True:
            result["write_denial_classification"] = "effective_denied_despite_posix_allow"
        else:
            result["write_denial_classification"] = "write_denied_cause_unverified"
        result["status"] = "no_go_no_effective_write"
    elif write is True and read is True:
        result["write_denial_classification"] = "no_access_denial_observed"
        result["status"] = "access_metadata_only_no_htp_proof"
    else:
        result["status"] = "no_go_no_effective_read"

    return result


if __name__ == "__main__":
    try:
        observed = diagnose()
    except Exception:
        # Never expose exception messages, paths, PIDs, raw ACL or IDs.
        observed = {
            "probe": "ventuno_secure_cdsp_fastrpc_acl_effective_readonly",
            "status": "metadata_exception_no_go",
            "device_opened": False,
            "device_written": False,
            "service_or_permissions_modified": False,
            "qnn_or_htp_executed": False,
            "npu_inference_verified": False,
        }
    print("MYAI_SECURE_FASTRPC_ACL_JSON=" + json.dumps(observed, sort_keys=True))
