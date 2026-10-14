"""Synthetic Linux ACL fixtures only; never opens real device nodes."""
import json
import os
import stat
import struct
from types import SimpleNamespace

from scripts import ventuno_dma_acl_effective_readonly as acl


def blob(entries, version=2):
    return struct.pack("<I", version) + b"".join(
        struct.pack("<HHI", tag, perm, ident) for tag, perm, ident in entries
    )


def example_acl():
    # Owner rw; named user 1001 rw; group owner r;
    # named group 44 w; mask rw; other none.
    return (
        (acl.TAG_USER_OBJ, 6, 0xffffffff),
        (acl.TAG_USER, 6, 1001),
        (acl.TAG_GROUP_OBJ, 4, 0xffffffff),
        (acl.TAG_GROUP, 2, 44),
        (acl.TAG_MASK, 6, 0xffffffff),
        (acl.TAG_OTHER, 0, 0xffffffff),
    )


def test_parse_acl_rejects_invalid_header_tags_and_duplicates():
    entries = example_acl()
    assert acl.parse_acl(blob(entries)) is not None
    assert acl.parse_acl(blob(entries, version=1)) is None
    assert acl.parse_acl(blob(entries) + b"x") is None
    assert acl.parse_acl(blob(entries) * 300) is None
    assert acl.parse_acl(blob(entries[:-1] + ((99, 7, 1),))) is None
    assert acl.parse_acl(blob(entries + (entries[0],))) is None


def test_parse_acl_named_entries_require_mask_and_valid_permissions():
    entries = tuple(x for x in example_acl() if x[0] != acl.TAG_MASK)
    assert acl.parse_acl(blob(entries)) is None
    modified = list(example_acl())
    modified[0] = (acl.TAG_USER_OBJ, 8, 0xffffffff)
    assert acl.parse_acl(blob(modified)) is None
    assert acl.parse_acl(b"secret") is None


def test_owner_rights_ignore_mask():
    parsed = acl.parse_acl(blob(example_acl()))
    assert acl.acl_permission(parsed, 123, 567, 123, 9, frozenset()) == {
        "read": True, "write": True,
    }


def test_named_user_precedes_group_even_when_group_would_grant_permission():
    parsed = acl.parse_acl(blob(example_acl()))
    rights = acl.acl_permission(
        parsed, 123, 567, 1001, 44, frozenset({44}),
    )
    assert rights == {"read": True, "write": True}


def test_group_union_and_mask_are_applied():
    parsed = acl.parse_acl(blob(example_acl()))
    both = acl.acl_permission(parsed, 123, 567, 900, 567, frozenset({44}))
    assert both == {"read": True, "write": True}
    write_only = acl.acl_permission(parsed, 123, 567, 900, 44, frozenset())
    assert write_only == {"read": False, "write": True}
    other = acl.acl_permission(parsed, 123, 567, 900, 999, frozenset())
    assert other == {"read": False, "write": False}


def test_fail_closed_without_valid_acl():
    assert acl.acl_permission(None, 1, 1, 1, 1, frozenset()) is None


def test_real_device_absent_denies_without_xattr(tmp_path, monkeypatch):
    monkeypatch.setattr(acl.os, "getxattr", lambda *_a, **_kw:
                        (_ for _ in ()).throw(AssertionError("xattr called")))
    report = acl.report(target=tmp_path / "missing")
    assert report["acl_status"] == "node_inaccessible"
    assert report["device_open_attempted"] is False


def test_real_device_required_not_regular_file(tmp_path, monkeypatch):
    path = tmp_path / "notdevice"
    path.write_text("sensitive", encoding="utf8")
    monkeypatch.setattr(acl.os, "getxattr", lambda *_a, **_kw:
                        (_ for _ in ()).throw(AssertionError("xattr called")))
    report = acl.report(target=path)
    assert report["acl_status"] == "not_character_device"


def test_report_emits_only_rights_no_acl_identity_or_bytes(monkeypatch):
    raw = blob(example_acl())
    class CharNode:
        def lstat(self):
            return SimpleNamespace(st_mode=stat.S_IFCHR | 0o640,
                                   st_uid=123, st_gid=567)
    monkeypatch.setattr(acl.os, "getxattr", lambda *_a, **_kw: raw)
    monkeypatch.setattr(acl.os, "geteuid", lambda: 1001)
    monkeypatch.setattr(acl.os, "getegid", lambda: 1234)
    monkeypatch.setattr(acl.os, "getgroups", lambda: [44])
    monkeypatch.setattr(acl.os, "access", lambda _p, flag, effective_ids:
                        True)
    monkeypatch.setattr(acl, "one_geniex_identity", lambda: {
        "fsuid": 900, "fsgid": 567, "groups": frozenset({44}),
    })
    output = acl.report(target=CharNode())
    assert output["acl_status"] == "posix_acl_v2_parsed"
    assert output["runner_acl_read"] is True
    assert output["runner_acl_write"] is True
    assert output["geniex_acl_read"] is True
    assert output["geniex_acl_write"] is True
    assert output["runner_acl_matches_effective_access"] is True
    assert output["acl_raw_exported"] is False
    assert output["ids_exported"] is False
    assert output["device_open_attempted"] is False
    assert output["qnn_inference_attempted"] is False
    serialized = json.dumps(output)
    for sensitive in ("1001", "1234", "567", "ACL_USER", "/dev/", "secret"):
        assert sensitive not in serialized
