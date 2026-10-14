"""Synthetic-only read-only v75 ELF and FastRPC package audit tests."""
import json
from pathlib import Path
import struct

from scripts import ventuno_v75_elf_fastrpc_readonly as probe


def elf_header(machine=164, elf_class=2, endian=1):
    raw = bytearray(64)
    raw[:4] = b"\x7fELF"
    raw[4] = elf_class
    raw[5] = endian
    raw[18:20] = struct.pack("<H", machine)
    return bytes(raw)


def test_header_distinguishes_hexagon_from_aarch64():
    assert probe.classify_elf_header(elf_header(164)) == "hexagon_elf_header"
    assert probe.classify_elf_header(elf_header(183)) == "aarch64_elf_header"
    assert probe.classify_elf_header(elf_header(3)) == "other_elf_header"
    assert probe.classify_elf_header(b"secret") == "not_elf_or_incomplete"
    assert probe.classify_elf_header(elf_header(164, endian=2)) == (
        "unsupported_elf_class_or_endian"
    )


def test_resolved_skel_header_within_test_root_never_returns_path(tmp_path, monkeypatch):
    root = tmp_path / "usr"
    target = root / "share" / "vendor" / "skel.so"
    target.parent.mkdir(parents=True)
    target.write_bytes(elf_header(164) + b"\0" * 1024)
    link = root / "libQnnHtpV75Skel.so"
    link.symlink_to(target)
    monkeypatch.setattr(probe, "package_owner", lambda path: "qairt-dsp-binaries")
    observed = probe.inspect_resolved_skel(link, root)
    assert observed["path_inside_usr"] is True
    assert observed["file_regular"] is True
    assert observed["library_file_header_read"] is True
    assert observed["header_class"] == "hexagon_elf_header"
    assert observed["package_owner"] == "qairt-dsp-binaries"
    assert str(tmp_path) not in json.dumps(observed)
    assert "vendor" not in json.dumps(observed)


def test_refuses_outside_scope_and_does_not_read(monkeypatch, tmp_path):
    root = tmp_path / "usr"
    root.mkdir()
    outside = tmp_path / "outside.so"
    outside.write_bytes(elf_header(164))
    link = root / "skel.so"
    link.symlink_to(outside)
    monkeypatch.setattr(
        probe.os, "open",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("external file was opened")
        ),
    )
    monkeypatch.setattr(
        probe, "package_owner",
        lambda _p: (_ for _ in ()).throw(
            AssertionError("out-of-scope package lookup")
        ),
    )
    observed = probe.inspect_resolved_skel(link, root)
    assert observed["path_inside_usr"] is False
    assert observed["library_file_header_read"] is False


def test_undersized_and_dangling_fail_closed(monkeypatch, tmp_path):
    root = tmp_path / "usr"
    root.mkdir()
    link = root / "skel.so"
    link.symlink_to("absent")
    assert probe.inspect_resolved_skel(link, root)["header_class"] == "unavailable"
    target = root / "tiny.so"
    target.write_bytes(b"x" * 10)
    link.unlink()
    link.symlink_to(target)
    monkeypatch.setattr(probe, "package_owner", lambda _p: "unverified")
    observed = probe.inspect_resolved_skel(link, root)
    assert observed["header_class"] == "size_outside_bound"
    assert observed["library_file_header_read"] is False


def test_shell_metadata_only_lstat(tmp_path):
    path = tmp_path / "shell"
    path.write_bytes(b"NEVER EXECUTE")
    link = tmp_path / "shell_link"
    link.symlink_to(path)
    observed = probe.shell_metadata({
        "regular": path, "symlink": link, "missing": tmp_path / "no",
    })
    assert observed == {
        "regular": "regular_file",
        "symlink": "symlink_unresolved",
        "missing": "absent",
    }


def test_dpkg_query_strict_package_allowlist_no_raw_messages(monkeypatch):
    calls = []
    monkeypatch.setattr(probe.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    class Fake:
        returncode = 0
        stdout = b"ii |1.0.15+repack2"
    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return Fake()
    monkeypatch.setattr(probe.subprocess, "run", run)
    result = probe.fastrpc_packages()
    assert set(result) == {"qcom-fastrpc1", "qcom-fastrpc-dev"}
    assert all(v == {"status": "installed", "version": "1.0.15+repack2"}
               for v in result.values())
    assert len(calls) == 2
    for argv, options in calls:
        assert argv[0] == "/usr/bin/dpkg-query"
        assert argv[1] == "-W"
        assert argv[-1] in probe.PACKAGES
        assert options["timeout"] == 5
        assert options["check"] is False
        assert options["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def test_summary_never_claims_firmware_or_pd_compatibility(monkeypatch):
    monkeypatch.setattr(probe, "inspect_resolved_skel", lambda: {
        "header_class": "hexagon_elf_header", "path_inside_usr": True,
        "file_regular": True, "package_owner": "qairt-dsp-binaries",
        "library_file_header_read": True,
    })
    monkeypatch.setattr(probe, "shell_metadata", lambda: {})
    monkeypatch.setattr(probe, "fastrpc_packages", lambda: {})
    r = probe.report()
    assert r["hexagon_header_is_only_format_indication"] is True
    assert r["dsp_signed_or_unsigned_pd_verified"] is False
    assert r["dsp_firmware_compatibility_verified"] is False
    assert r["qnn_htp_runtime_backend_verified"] is False
    assert r["no_device_node_opened"] is True
    assert r["no_production_services_changed"] is True
    assert r["raw_file_bytes_or_paths_exported"] is False
    assert "/usr/" not in json.dumps(r)
