"""Only synthetic metadata: never read real device ACLs or run QNN."""
import errno
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace

from scripts import ventuno_fastrpc_acl_root_readonly as probe


def test_rule_root_symlink_alias_is_detected_without_content_read(tmp_path):
    etc = tmp_path / "etc"
    vendor = tmp_path / "vendor"
    link = tmp_path / "lib"
    etc.mkdir()
    vendor.mkdir()
    link.symlink_to(vendor, target_is_directory=True)
    result = probe.classify_rule_roots({
        "etc": etc, "usr_lib": vendor, "lib": link,
    })
    assert result["root_types"] == {
        "etc": "directory", "usr_lib": "directory", "lib": "symlink",
    }
    assert result["lib_aliases_usr_lib"] is True
    assert str(tmp_path) not in json.dumps(result)


def test_rule_root_missing_does_not_fake_alias(tmp_path):
    result = probe.classify_rule_roots({
        "etc": tmp_path / "absent",
        "usr_lib": tmp_path / "missing_vendor",
        "lib": tmp_path / "also_missing",
    })
    assert result["lib_aliases_usr_lib"] is None
    assert all(v == "missing" for v in result["root_types"].values())


def test_acl_present_discards_raw_bytes(monkeypatch):
    class CharNode:
        def lstat(self):
            return SimpleNamespace(st_mode=stat.S_IFCHR | 0o640)
    monkeypatch.setattr(
        probe.os, "getxattr",
        lambda *_args, **_kwargs: b"PRIVATE-ACL-CONTENT",
    )
    result = probe.acl_indicator(CharNode())
    assert result == "acl_present"
    assert "PRIVATE" not in result


def test_acl_not_exposed_and_unsupported_are_not_claimed_absent(monkeypatch):
    class CharNode:
        def lstat(self):
            return SimpleNamespace(st_mode=stat.S_IFCHR | 0o640)
    def raised(code):
        def fail(*_a, **_k):
            raise OSError(code, "fake")
        return fail
    monkeypatch.setattr(probe.os, "getxattr", raised(errno.ENODATA))
    assert probe.acl_indicator(CharNode()) == "not_exposed"
    monkeypatch.setattr(probe.os, "getxattr", raised(errno.EOPNOTSUPP))
    assert probe.acl_indicator(CharNode()) == "unsupported"
    monkeypatch.setattr(probe.os, "getxattr", raised(errno.EACCES))
    assert probe.acl_indicator(CharNode()) == "unavailable"


def test_acl_non_device_does_not_call_getxattr(monkeypatch, tmp_path):
    path = tmp_path / "data.txt"
    path.write_text("not a char device", encoding="ascii")
    monkeypatch.setattr(probe.os, "getxattr", lambda *_a, **_k: (
        _ for _ in ()).throw(AssertionError("non-device xattr")))
    assert probe.acl_indicator(path) == "not_character_device"
    assert probe.acl_indicator(tmp_path / "missing") == "device_absent_or_inaccessible"


def test_capabilities_read_only_bool_with_bounded_status(tmp_path):
    path = tmp_path / "status"
    path.write_bytes(b"Name:\tsynthetic\nCapEff:\t0000000000000000\n")
    assert probe.effective_capabilities_indicator(path) is False
    path.write_bytes(b"CapEff:\t0000000000000010\n")
    assert probe.effective_capabilities_indicator(path) is True
    path.write_bytes(b"CapEff:invalid\n")
    assert probe.effective_capabilities_indicator(path) is None
    path.write_bytes(b"CapEff:\t0000000000000010\n" * 900)
    assert probe.effective_capabilities_indicator(path) is None


def test_report_is_metadata_only_no_identifiers(monkeypatch, tmp_path):
    monkeypatch.setattr(probe, "fastrpc_gid", lambda: 40)
    monkeypatch.setattr(probe, "one_geniex_identity", lambda: {
        "fsuid": 1001, "fsgid": 1001, "groups": frozenset({40}),
    })
    monkeypatch.setattr(probe, "metadata_for_device", lambda *a, **kw: {
        "runner_has_classic_dac_write": False,
        "runner_effective_write_access": True,
        "geniex_has_classic_dac_write": False,
    })
    monkeypatch.setattr(probe, "acl_indicator", lambda path: "acl_present")
    monkeypatch.setattr(probe, "geniex_effective_caps", lambda: False)
    monkeypatch.setattr(probe, "effective_capabilities_indicator", lambda _: False)
    root = tmp_path / "dev"
    report = probe.report(dev_root=root, rule_roots={
        "etc": tmp_path / "missing1",
        "usr_lib": tmp_path / "missing2",
        "lib": tmp_path / "missing3",
    })
    assert report["dma_heap_runner_write_effective_but_classic_dac_denied"] is True
    assert report["dma_heap_acl_indicator"] == "acl_present"
    assert report["device_open_attempted"] is False
    assert report["qnn_or_htp_attempted"] is False
    assert report["production_modified"] is False
    encoded = json.dumps(report)
    assert str(tmp_path) not in encoded
    assert "1001" not in encoded
    assert "private" not in encoded.lower()
