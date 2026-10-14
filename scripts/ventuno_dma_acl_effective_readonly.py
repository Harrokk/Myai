"""Resolve bounded POSIX ACL effective permissions for known DMA-heap node.

No device open, QNN, audio, service mutation or raw ACL/PID/UID disclosure.
Implements only the Linux POSIX ACL xattr v2 disk format; any malformed or
ambiguous ACL yields unknown rather than a guessed effective right.
"""
import errno
import json
import os
from pathlib import Path
import stat
import struct

from scripts.ventuno_fastrpc_policy_readonly import one_geniex_identity

VERSION = 2
MAX_ACL_BYTES = 4096
TAG_USER_OBJ = 0x01
TAG_USER = 0x02
TAG_GROUP_OBJ = 0x04
TAG_GROUP = 0x08
TAG_MASK = 0x10
TAG_OTHER = 0x20
TAGS = {TAG_USER_OBJ, TAG_USER, TAG_GROUP_OBJ, TAG_GROUP, TAG_MASK, TAG_OTHER}
BASE_TAGS = {TAG_USER_OBJ, TAG_GROUP_OBJ, TAG_OTHER, TAG_MASK}
TARGET = Path("/dev/dma_heap/system")


def parse_acl(raw):
    """Return private parsed entries, or None for anything unverifiable."""
    if not isinstance(raw, bytes) or len(raw) < 28:
        return None
    if len(raw) > MAX_ACL_BYTES or (len(raw) - 4) % 8:
        return None
    if struct.unpack_from("<I", raw, 0)[0] != VERSION:
        return None
    entries = []
    seen_base = set()
    seen_named = set()
    for offset in range(4, len(raw), 8):
        tag, perm, identity = struct.unpack_from("<HHI", raw, offset)
        if tag not in TAGS or perm > 7:
            return None
        if tag in BASE_TAGS:
            if tag in seen_base:
                return None
            seen_base.add(tag)
        elif (tag, identity) in seen_named:
            return None
        else:
            seen_named.add((tag, identity))
        entries.append((tag, perm, identity))
    if not {TAG_USER_OBJ, TAG_GROUP_OBJ, TAG_OTHER}.issubset(seen_base):
        return None
    if seen_named and TAG_MASK not in seen_base:
        return None
    return tuple(entries)


def acl_permission(entries, owner_uid, owner_gid, fsuid, fsgid, groups):
    """Evaluate standard POSIX ACL precedence; never emit identity fields."""
    if not entries:
        return None
    base = {tag: perm for tag, perm, _ in entries if tag in BASE_TAGS}
    mask = base.get(TAG_MASK, 7)
    if fsuid == owner_uid:
        bits = base[TAG_USER_OBJ]
    else:
        named_users = [
            perm for tag, perm, identity in entries
            if tag == TAG_USER and identity == fsuid
        ]
        if named_users:
            bits = named_users[0] & mask
        else:
            memberships = set(groups)
            memberships.add(fsgid)
            selected = []
            if owner_gid in memberships:
                selected.append(base[TAG_GROUP_OBJ])
            selected.extend(
                perm for tag, perm, identity in entries
                if tag == TAG_GROUP and identity in memberships
            )
            bits = (0 if not selected else
                    __import__("functools").reduce(lambda a, b: a | b, selected, 0) & mask)
            if not selected:
                bits = base[TAG_OTHER]
    return {"read": bool(bits & 4), "write": bool(bits & 2)}


def report(target=TARGET):
    result = {
        "probe": "ventuno_dma_heap_acl_permission_outcomes_only",
        "char_device_validated": False,
        "acl_status": "unknown",
        "runner_acl_read": None,
        "runner_acl_write": None,
        "runner_effective_read": None,
        "runner_effective_write": None,
        "runner_acl_matches_effective_access": None,
        "one_geniex_identity_available": False,
        "geniex_acl_read": None,
        "geniex_acl_write": None,
        "acl_raw_exported": False,
        "ids_exported": False,
        "device_open_attempted": False,
        "qnn_inference_attempted": False,
        "production_modified": False,
    }
    try:
        st = target.lstat()
    except OSError:
        result["acl_status"] = "node_inaccessible"
        return result
    if not stat.S_ISCHR(st.st_mode):
        result["acl_status"] = "not_character_device"
        return result
    result["char_device_validated"] = True
    try:
        raw = os.getxattr(target, "system.posix_acl_access", follow_symlinks=False)
    except OSError as exc:
        if exc.errno in {errno.ENODATA, getattr(errno, "ENOATTR", errno.ENODATA)}:
            result["acl_status"] = "acl_not_exposed"
        else:
            result["acl_status"] = "acl_unavailable"
        return result
    except (TypeError, NotImplementedError):
        result["acl_status"] = "acl_unavailable"
        return result
    acl = parse_acl(raw)
    if acl is None:
        result["acl_status"] = "unrecognized_acl_format"
        return result
    result["acl_status"] = "posix_acl_v2_parsed"
    runner = acl_permission(
        acl, st.st_uid, st.st_gid,
        os.geteuid(), os.getegid(), frozenset(os.getgroups()),
    )
    result["runner_acl_read"] = runner["read"]
    result["runner_acl_write"] = runner["write"]
    try:
        result["runner_effective_read"] = os.access(
            target, os.R_OK, effective_ids=True
        )
        result["runner_effective_write"] = os.access(
            target, os.W_OK, effective_ids=True
        )
        result["runner_acl_matches_effective_access"] = (
            result["runner_acl_read"] == result["runner_effective_read"]
            and result["runner_acl_write"] == result["runner_effective_write"]
        )
    except (OSError, NotImplementedError, TypeError, ValueError):
        pass
    geniex = one_geniex_identity()
    if geniex is not None:
        result["one_geniex_identity_available"] = True
        allowed = acl_permission(
            acl, st.st_uid, st.st_gid,
            geniex["fsuid"], geniex["fsgid"], geniex["groups"],
        )
        result["geniex_acl_read"] = allowed["read"]
        result["geniex_acl_write"] = allowed["write"]
    return result


if __name__ == "__main__":
    print("MYAI_DMA_ACL_OUTCOMES_JSON=" + json.dumps(report(), sort_keys=True))
