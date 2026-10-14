"""Synthetic-only V75 skel link provenance checks; never invoke QNN."""
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import ventuno_htp_v75_skel_link_readonly as probe


def test_relative_symlink_into_vendor_tree(tmp_path):
    vendor = tmp_path / "dsp"
    vendor.mkdir()
    target = vendor / "actual-skel.so"
    target.write_bytes(b"NOT_EXECUTED")
    link = vendor / "libQnnHtpV75Skel.so"
    link.symlink_to("actual-skel.so")
    data = probe.inspect_path(link, vendor)
    assert data["kind"] == "symlink"
    assert data["resolved_regular_file"] is True
    assert data["resolved_within_trusted_tree"] is True
    assert "actual-skel" not in json.dumps(data)


def test_symlink_escape_not_assumed_safe(tmp_path):
    vendor = tmp_path / "dsp"
    vendor.mkdir()
    outside = tmp_path / "outside"
    outside.write_bytes(b"x")
    link = vendor / "libQnnHtpV75Skel.so"
    link.symlink_to(outside)
    data = probe.inspect_path(link, vendor)
    assert data["kind"] == "symlink"
    assert data["resolved_regular_file"] is True
    assert data["resolved_within_trusted_tree"] is False


def test_dangling_and_nonregular_are_not_success(tmp_path):
    vendor = tmp_path / "dsp"
    vendor.mkdir()
    link = vendor / "libQnnHtpV75Skel.so"
    link.symlink_to("missing")
    data = probe.inspect_path(link, vendor)
    assert data["kind"] == "symlink_dangling_or_unavailable"
    assert data["resolved_regular_file"] is False
    directory = vendor / "folder"
    directory.mkdir()
    assert probe.inspect_path(directory, vendor)["kind"] == "unexpected_file_type"
    assert probe.inspect_path(vendor / "absent", vendor)["kind"] == "absent"


def test_dpdk_owner_only_allowlisted_values(monkeypatch):
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    calls = []
    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0,
                               stdout=b"qairt-dsp-binaries: /usr/lib/dsp/cdsp/file")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    assert probe.package_owner(Path("/usr/lib/dsp/cdsp/libQnnHtpV75Skel.so")) == (
        "qairt-dsp-binaries"
    )
    assert calls[0][0][1] == "-S"
    assert calls[0][1]["timeout"] == 5
    assert calls[0][1]["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def test_owner_nonwhitelisted_and_multiline_are_not_exported(monkeypatch):
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    value = {"output": b"private: /secret/path"}
    def fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout=value["output"])
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    assert probe.package_owner(probe.SKEL) == "different_or_qualified_package"
    value["output"] = b"qairt-libs: /one\nqairt-dsp-binaries: /two"
    assert probe.package_owner(probe.SKEL) == "unverified"
    value["output"] = b"x" * (probe.MAX_OUTPUT + 1)
    assert probe.package_owner(probe.SKEL) == "unverified"


def test_report_contains_only_metadata(monkeypatch):
    monkeypatch.setattr(probe, "inspect_path", lambda path, root: {
        "kind": "symlink", "resolved_regular_file": True,
        "resolved_within_trusted_tree": True,
        "resolved_target_recorded": False,
    })
    monkeypatch.setattr(probe, "package_owner", lambda _: "qairt-libs")
    result = probe.report()
    assert result["v75_skel_regular_file_in_vendor_dsp_tree"] is True
    assert result["qnn_htp_inference_attempted"] is False
    assert result["device_or_library_opened"] is False
    assert result["stub_skel_version_compatibility_proven"] is False
    assert "/usr/lib/" not in json.dumps(result)


def test_resolved_target_region_returns_only_category(tmp_path):
    vendor = tmp_path / "vendor"
    dsp = vendor / "dsp"
    firmware = vendor / "firmware"
    dsp.mkdir(parents=True)
    firmware.mkdir()
    binary = firmware / "actual.so"
    binary.write_bytes(b"NEVER-LOADED")
    link = dsp / "skel.so"
    link.symlink_to(binary)
    region, resolved = probe.classify_resolved_location(link, {
        "firmware": firmware, "vendor": vendor,
    })
    assert region == "firmware"
    assert resolved == binary
    assert str(binary) not in region


def test_untrusted_resolved_target_does_not_reveal_path(tmp_path):
    trusted = tmp_path / "trusted"
    trusted.mkdir()
    other = tmp_path / "private"
    other.write_bytes(b"secret")
    link = trusted / "libQnnHtpV75Skel.so"
    link.symlink_to(other)
    category, resolved = probe.classify_resolved_location(link, {
        "only_trusted": trusted,
    })
    assert category == "outside_sampled_system_roots"
    assert resolved is None
    assert str(other) not in category


def test_unresolvable_target_is_unknown_not_negative(tmp_path):
    link = tmp_path / "missing.so"
    link.symlink_to("absent.so")
    category, target = probe.classify_resolved_location(link, {
        "one": tmp_path,
    })
    assert category == "unavailable"
    assert target is None


def test_broad_target_zone_never_exports_path(tmp_path):
    target = tmp_path / "SECRET-FILENAME.so"
    target.write_bytes(b"NOTLOADED")
    link = tmp_path / "skel-link.so"
    link.symlink_to(target)
    zone = probe.broad_resolved_target_zone(link)
    assert zone == "tmp"
    assert "SECRET" not in zone
    assert str(tmp_path) not in zone


def test_broad_zone_fails_closed_on_missing_target(tmp_path):
    link = tmp_path / "skel-link.so"
    link.symlink_to("missing")
    assert probe.broad_resolved_target_zone(link) == "unavailable"
