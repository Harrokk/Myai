"""Synthetic-only QNN package metadata tests; no real QNN/HTP invocation."""
from pathlib import Path
from types import SimpleNamespace
import json
import stat

from scripts import ventuno_qairt_v75_package_readonly as probe


def test_package_status_requires_installed_and_sanitized_version():
    assert probe.classify_package_output(0, b"ii |2.45.1-1") == {
        "status": "installed", "version": "2.45.1-1",
    }
    assert probe.classify_package_output(1, b"ii |2.45.1-1")["version"] is None
    assert probe.classify_package_output(0, b"rc |2.45.1-1")["status"] != "installed"
    assert probe.classify_package_output(0, b"ii |SECRET /tmp/private")["version"] is None
    assert probe.classify_package_output(0, b"ii |" + b"x" * 500)["version"] is None


def test_package_query_reads_only_whitelisted_names(monkeypatch):
    calls = []
    monkeypatch.setattr(probe.shutil, "which", lambda n: "/usr/bin/dpkg-query")
    def fake_run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=0, stdout=b"ii |2.45.0")
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    results = probe.package_versions()
    assert set(results) == set(probe.PACKAGE_NAMES)
    assert all(x["status"] == "installed" for x in results.values())
    for argv, kwargs in calls:
        assert argv[0] == "/usr/bin/dpkg-query"
        assert argv[-1] in probe.PACKAGE_NAMES
        assert argv[1] == "-W"
        assert kwargs["timeout"] == 5
        assert kwargs["check"] is False
        assert kwargs["env"] == {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def test_no_dpkg_query_executable_returns_unknown_not_false(monkeypatch):
    monkeypatch.setattr(probe.shutil, "which", lambda _: None)
    result = probe.package_versions()
    assert all(x["status"] == "tool_unavailable" for x in result.values())


def test_exact_sampled_paths_only_lstat_no_library_loading(tmp_path, monkeypatch):
    root = tmp_path / "qnn"
    root.mkdir()
    (root / "libQnnHtpV75Skel.so").write_bytes(b"DO-NOT-OPEN")
    (root / "libQnnHtp.so").symlink_to("secret-target")
    result = probe.sampled_artifacts({"only": root})
    assert result["only"]["libQnnHtpV75Skel.so"] == "regular_file"
    assert result["only"]["libQnnHtp.so"] == "symlink_unresolved"
    assert result["only"]["libQnnCpu.so"] == "absent"
    assert len(result["only"]) == len(probe.FILE_NAMES)
    assert "secret-target" not in json.dumps(result)
    assert str(tmp_path) not in json.dumps(result)


def test_package_partial_not_equated_to_runtime_failure():
    p = {
        "qairt-libs": {"status": "installed", "version": "2.45"},
        "qairt-dsp-binaries": {"status": "not_installed_or_unverified", "version": None},
    }
    libs = {"usr_lib_dsp_cdsp": {
        "libQnnHtpV75Skel.so": "regular_file",
        "libQnnHtp.so": "symlink_unresolved",
    }}
    report = probe.summarize(p, libs)
    assert report["v75_skel_in_sampled_paths"] is True
    assert report["htp_host_lib_in_sampled_paths"] is True
    assert report["arduino_documented_qairt_packages_installed"] is False
    assert report["dsp_host_firmware_compatibility_proven"] is False
    assert report["qnn_or_htp_executed"] is False


def test_empty_metadata_does_not_assert_backend_success():
    report = probe.summarize({}, {})
    assert report["v75_skel_in_sampled_paths"] is False
    assert report["installed_runtime_matches_synthetic_dlc_sdk_proven"] is False
    assert report["dsp_process_domain_policy_verified"] is False
    assert report["software_installed_or_modified"] is False
