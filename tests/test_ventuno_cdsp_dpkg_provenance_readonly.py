"""Synthetic-only package provenance; no actual firmware binary is read."""
import json
from pathlib import Path
from types import SimpleNamespace

from scripts import ventuno_cdsp_dpkg_provenance_readonly as p


def make_cdsp(tmp_path, name="vendor/cdsp.mbn"):
    node = tmp_path / "remoteproc0"
    dt = node / "device" / "of_node"
    dt.mkdir(parents=True)
    (node / "name").write_text("opaque")
    (dt / "compatible").write_bytes(b"qcom,monaco-cdsp-pas\0")
    (node / "state").write_text("running")
    (node / "firmware").write_text(name)
    return tmp_path


def test_owner_parser_accepts_one_matching_allowlisted_record():
    target = Path("/lib/firmware/vendor/cdsp.mbn")
    assert p.parse_owner_record(
        b"firmware-qcom-soc: /lib/firmware/vendor/cdsp.mbn", target
    ) == ("allowlisted_package", "firmware-qcom-soc")
    assert p.parse_owner_record(
        b"qairt-dsp-binaries:arm64: /lib/firmware/vendor/cdsp.mbn", target
    ) == ("allowlisted_package", "qairt-dsp-binaries")


def test_owner_parser_never_reports_raw_unsafe_response():
    target = Path("/lib/firmware/vendor/cdsp.mbn")
    for raw in (
        b"private: /secrets/abc",
        b"firmware-qcom-soc: /wrong",
        b"firmware-qcom-soc: /lib/firmware/vendor/cdsp.mbn\nOTHER: /secret",
        b"firmware-qcom-soc: /lib/firmware/vendor/cdsp.mbn" + b"X" * 10000,
        b"\xff\xfe\xff",
    ):
        answer = p.parse_owner_record(raw, target)
        assert answer == ("unverified", None)
        assert "/secret" not in json.dumps(answer)
    assert p.parse_owner_record(
        b"company-private: /lib/firmware/vendor/cdsp.mbn", target
    ) == ("other_dpkg_package", None)


def test_dpkg_query_only_exact_path_and_no_shell(monkeypatch):
    calls = []
    monkeypatch.setattr(p.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    def fake_run(argv, **opts):
        calls.append((argv, opts))
        return SimpleNamespace(returncode=0,
                               stdout=f"linux-firmware: {argv[-1]}".encode())
    monkeypatch.setattr(p.subprocess, "run", fake_run)
    result = p.dpkg_owner(Path("/lib/firmware/vendor/cdsp.mbn"))
    assert result == ("allowlisted_package", "linux-firmware")
    assert len(calls) == 1
    assert calls[0][0][1] == "-S"
    assert calls[0][1]["timeout"] == 5
    assert calls[0][1]["check"] is False
    assert calls[0][1]["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def test_package_version_cannot_query_unallowlisted_names(monkeypatch):
    monkeypatch.setattr(p.subprocess, "run", lambda *_a, **_k:
                        (_ for _ in ()).throw(AssertionError("Must not query")))
    assert p.package_version("private-secret") is None


def test_package_version_parses_sanitized_debian_strings(monkeypatch):
    monkeypatch.setattr(p.shutil, "which", lambda _: "/usr/bin/dpkg-query")
    calls = []
    def fake_run(argv, **opts):
        calls.append(argv)
        return SimpleNamespace(returncode=0, stdout=b"ii |2026.09-0ubuntu1")
    monkeypatch.setattr(p.subprocess, "run", fake_run)
    assert p.package_version("firmware-qcom-soc") == "2026.09-0ubuntu1"
    assert calls[0][-1] == "firmware-qcom-soc"


def test_four_candidate_paths_only_and_no_binary_reads(tmp_path):
    root = tmp_path / "firmware"
    file = root / "updates" / "6.8-qcom" / "vendor" / "cdsp.mbn"
    file.parent.mkdir(parents=True)
    file.write_bytes(b"NEVER READ")
    pairs = p.candidates(["vendor", "cdsp.mbn"], root, release="6.8-qcom")
    assert len(pairs) == 1
    assert pairs[0][1] == file
    assert p.candidates(["vendor", "cdsp.mbn"], root,
                        release="untrusted/release") == []


def test_provenance_of_regular_file_and_shell_without_raw_paths(
        tmp_path, monkeypatch):
    remote = make_cdsp(tmp_path / "proc")
    firmware = tmp_path / "firmware"
    binary = firmware / "vendor" / "cdsp.mbn"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"PRIVATE_FIRMWARE_CONTENT")
    usr = tmp_path / "usr"
    shell = usr / "lib" / "dsp" / "cdsp" / "fastrpc_shell_unsigned_3"
    shell.parent.mkdir(parents=True)
    shell.write_bytes(b"PRIVATE_SHELL_CONTENT")
    monkeypatch.setattr(p, "USR_ROOT", usr)
    monkeypatch.setattr(p, "dpkg_owner", lambda path: (
        ("allowlisted_package", "firmware-qcom-soc")
        if path.name == "cdsp.mbn" else
        ("allowlisted_package", "qairt-dsp-binaries")
    ))
    monkeypatch.setattr(p, "package_version", lambda package: (
        "2026.10" if package == "firmware-qcom-soc" else "2.46.0"
    ))
    result = p.report(remote_root=remote, firmware_root=firmware, shell=shell)
    assert result["firmware_package_family"] == "qcom_firmware"
    assert result["firmware_package_version"] == "2026.10"
    assert result["shell_package_family"] == "qairt_dsp_binaries"
    assert result["shell_target"] == "regular_file_under_usr"
    assert result["matching_firmware_build_and_shell_verified"] is False
    assert result["device_opened"] is False
    assert result["firmware_payload_read"] is False
    data = json.dumps(result)
    assert "PRIVATE" not in data
    assert str(tmp_path) not in data
    assert "/vendor/" not in data


def test_unknown_owner_not_treated_as_missing_image(tmp_path, monkeypatch):
    remote = make_cdsp(tmp_path / "proc")
    firmware = tmp_path / "firmware"
    binary = firmware / "vendor" / "cdsp.mbn"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"content")
    monkeypatch.setattr(p, "dpkg_owner",
                        lambda _: ("not_listed_in_dpkg", None))
    result = p.report(remote_root=remote, firmware_root=firmware,
                      shell=tmp_path / "no-shell")
    assert result["running_cdsp_identified"] is True
    assert result["regular_firmware_candidates_examined"] == 1
    assert result["firmware_package_provenance"] == (
        "not_listed_in_sampled_dpkg_paths"
    )
    assert result["running_firmware_binary_verified"] is False


def test_invalid_firmware_name_prevents_any_lookup(monkeypatch, tmp_path):
    remote = make_cdsp(tmp_path / "proc", name="../private-key")
    monkeypatch.setattr(p, "file_provenance",
                        lambda *_: (_ for _ in ()).throw(
                            AssertionError("No firmware query expected")
                        ))
    result = p.report(
        remote_root=remote, firmware_root=tmp_path,
        shell=tmp_path / "missing-shell",
    )
    assert result["firmware_name_usable"] is False
    assert result["regular_firmware_candidates_examined"] == 0
    assert result["firmware_package_provenance"] == "not_checked"


def test_ambiguous_firmware_candidates_are_not_conflated(monkeypatch, tmp_path):
    remote = make_cdsp(tmp_path / "proc")
    firmware = tmp_path / "firmware"
    files = []
    for branch in ("updates", "other"):
        path = firmware / branch / "vendor" / "cdsp.mbn"
        path.parent.mkdir(parents=True)
        path.write_bytes(b"a")
        files.append(path)
    monkeypatch.setattr(p, "candidates", lambda name, root: [
        (files[0], files[0]), (files[1], files[1])
    ])
    monkeypatch.setattr(p, "file_provenance", lambda source, target: {
        "status": "allowlisted_package",
        "package_family": "qcom_firmware" if source == files[0]
                          else "linux_firmware",
        "package_version": "2026.10",
    })
    result = p.report(remote_root=remote, firmware_root=firmware,
                      shell=tmp_path / "missing")
    assert result["multiple_firmware_candidate_packages"] is True
    assert result["firmware_package_provenance"] == "ambiguous_candidates"
    assert result["firmware_package_family"] is None
