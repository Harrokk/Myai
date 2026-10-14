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
