"""Synthetic-only /dev/fastrpc-cdsp-secure ACL attribution regressions.

No real device path, device open, model, service or NPU is touched.
"""
import errno
import json
import stat
import struct
from types import SimpleNamespace

import pytest

from scripts import ventuno_secure_fastrpc_acl_effective_readonly as gate
from scripts.ventuno_dma_acl_effective_readonly import (
    TAG_USER_OBJ, TAG_GROUP_OBJ, TAG_MASK, TAG_OTHER,
)


class FakeDevice:
    def __init__(self, mode, *, inode=10):
        self.mode = mode
        self.inode = inode
        self.calls = 0

    def lstat(self):
        self.calls += 1
        return SimpleNamespace(
            st_mode=self.mode, st_uid=102, st_gid=202,
            st_dev=301, st_ino=self.inode
        )


def acl(*parts):
    return struct.pack("<I", 2) + b"".join(
        struct.pack("<HHI", tag, bits, 0) for tag, bits in parts
    )


def setup(monkeypatch, *, write=False, acl_payload=None, mode=0o660):
    device = FakeDevice(stat.S_IFCHR | mode)
    monkeypatch.setattr(gate.os, "geteuid", lambda: 501)
    monkeypatch.setattr(gate.os, "getegid", lambda: 202)
    monkeypatch.setattr(gate.os, "getgroups", lambda: [202])
    checks = []
    def os_access(path, flag, *, effective_ids):
        assert path is device
        assert effective_ids is True
        checks.append(flag)
        return True if flag == gate.os.R_OK else write
    monkeypatch.setattr(gate.os, "access", os_access)

    def getxattr(path, name, *, follow_symlinks):
        assert path is device and name == "system.posix_acl_access"
        assert follow_symlinks is False
        if acl_payload is None:
            raise OSError(errno.ENODATA, "no ACL")
        if isinstance(acl_payload, BaseException):
            raise acl_payload
        return acl_payload
    monkeypatch.setattr(gate.os, "getxattr", getxattr)
    return device, checks


def test_no_acl_classic_group_dac_denial_is_classified(monkeypatch):
    dev, calls = setup(monkeypatch, mode=0o640)
    r = gate.diagnose(dev)
    assert r["status"] == "metadata_read_only_no_htp_conclusion"
    assert r["acl_state"] == "no_extended_posix_acl"
    assert r["classic_mode_runner_write"] is False
    assert r["posix_effective_runner_write"] is False
    assert r["write_denial_classification"] == "classic_mode_write_denied"
    assert calls == [gate.os.R_OK, gate.os.W_OK]
    assert dev.calls == 2


def test_extended_acl_mask_blocks_write_despite_group_mode(monkeypatch):
    payload = acl((TAG_USER_OBJ, 6), (TAG_GROUP_OBJ, 6),
                  (TAG_MASK, 4), (TAG_OTHER, 0))
    dev, _ = setup(monkeypatch, mode=0o660, acl_payload=payload)
    r = gate.diagnose(dev)
    assert r["acl_state"] == "posix_acl_v2_parsed"
    assert r["classic_mode_runner_write"] is True
    assert r["posix_effective_runner_write"] is False
    assert r["effective_access_runner_write"] is False
    assert r["write_denial_classification"] == "posix_acl_write_denied"


def test_posix_allow_but_kernel_effective_denial_is_not_misattributed(monkeypatch):
    dev, _ = setup(monkeypatch, mode=0o660)
    r = gate.diagnose(dev)
    assert r["classic_mode_runner_write"] is True
    assert r["posix_effective_runner_write"] is True
    assert r["effective_access_runner_write"] is False
    assert r["write_denial_classification"] == "effective_denied_despite_posix_allow"
    assert r["posix_effective_matches_os_access"] is False


@pytest.mark.parametrize("error, expected", [
    (OSError(errno.EACCES, "SECRET Path /dev"), "acl_metadata_unavailable"),
    (OSError(errno.EOPNOTSUPP, "unsupported"), "posix_acl_unsupported"),
])
def test_unknown_acl_remains_unknown(error, expected, monkeypatch):
    dev, _ = setup(monkeypatch, mode=0o660, acl_payload=error)
    r = gate.diagnose(dev)
    assert r["acl_state"] == expected
    assert r["posix_effective_runner_write"] is None
    assert r["write_denial_classification"] == "write_denied_cause_unverified"
    assert "SECRET" not in json.dumps(r)


def test_malformed_acl_cannot_manufacture_permission(monkeypatch):
    dev, _ = setup(monkeypatch, acl_payload=b"SECRET_INVALID_ACL")
    r = gate.diagnose(dev)
    assert r["acl_state"] == "acl_format_unrecognized"
    assert r["posix_effective_runner_read"] is None
    assert r["status"] == "metadata_read_only_no_htp_conclusion"
    assert "SECRET" not in json.dumps(r)


def test_non_character_target_never_queries_acl_or_access(monkeypatch):
    dev, _ = setup(monkeypatch, mode=0o660)
    dev.mode = stat.S_IFREG | 0o660
    def no_xattr(*args, **kwargs):
        pytest.fail("Should not inspect ordinary file as device")
    monkeypatch.setattr(gate.os, "getxattr", no_xattr)
    assert gate.diagnose(dev)["status"] == "reject_non_character_device"


def test_device_race_fails_closed_without_asserted_dac_comparison(monkeypatch):
    dev, _ = setup(monkeypatch, mode=0o660, write=True)
    original = dev.lstat
    def changing():
        info = original()
        if dev.calls == 2:
            info.st_ino = 999
        return info
    dev.lstat = changing
    r = gate.diagnose(dev)
    assert r["status"] == "device_identity_changed"
    assert r["character_device_verified"] is False
    assert r["effective_access_runner_write"] is None


def test_positive_access_still_never_claims_htp_activation(monkeypatch):
    dev, _ = setup(monkeypatch, mode=0o660, write=True)
    r = gate.diagnose(dev)
    assert r["status"] == "access_metadata_only_no_htp_proof"
    assert r["npu_inference_verified"] is False
    assert r["qnn_or_htp_executed"] is False
    assert r["device_opened"] is False
    assert r["device_written"] is False
    assert r["service_or_permissions_modified"] is False
    assert r["acl_or_identity_exported"] is False


def test_missing_device_is_inconclusive(monkeypatch):
    class Missing:
        def lstat(self):
            raise FileNotFoundError("SECRET DEVICE PATH")
    r = gate.diagnose(Missing())
    assert r["status"] == "device_unavailable"
    assert "SECRET" not in json.dumps(r)
