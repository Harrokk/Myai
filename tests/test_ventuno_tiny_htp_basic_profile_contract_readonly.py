"""No hardware or model execution: synthetic tiny QNN HTP profiler gates."""
from pathlib import Path
import json
import pytest
from scripts import ventuno_tiny_htp_basic_profile_contract_readonly as gate


def good():
    return {
        "packages": {
            "qairt-libs": {"status": "installed", "version": "2.46.0-0ubuntu1"},
            "qairt-dsp-binaries": {"status": "installed", "version": "2.46.0-0ubuntu1"},
        },
        "verified_fixture": {"file_identity_verified": True},
        "hostlibs": {x: object() for x in gate.LIBS},
        "skel": True,
        "reader": {"usr_lib": True, "multiarch": False},
        "netrun_flags": frozenset(gate.NETRUN_FLAGS),
        "viewer_flags": frozenset(gate.VIEWER_FLAGS),
        "geniex": {
            "service_mainpid_present": True,
            "geniex_process_count": 1,
            "complete_fast_rpc_fd_scan": True,
            "complete_process_maps": True,
            "fast_rpc_secure_fd_open": True,
        },
        "free_kib": 9 * 1048576,
        "machine": "aarch64",
    }


def test_every_precondition_good_but_live_geniex_forbids_second_htp_client():
    r = gate.classify(**good())
    assert r["status"] == "no_go_htp_profiling_requires_exclusive_verified_run"
    assert r["runtime_pair_is_246"]
    assert r["dlc_format_forward_compatible"]
    assert r["sha_attested_16004_byte_tiny_dlc"]
    assert r["packaged_htp_host_libraries_verified"]
    assert r["packaged_v75_dsp_skel_verified"]
    assert r["packaged_htp_reader_found"]
    assert r["netrun_basic_capture_cli_supported"]
    assert r["viewer_htp_reader_cli_supported"]
    assert "no_go_existing_geniex_fastrpc_busy" in r["blockers"]
    assert "exclusive_vendor_approved_htp_window_not_attested" in r["blockers"]
    assert r["qnn_or_htp_executed"] is False
    assert r["htp_profile_log_generated"] is False
    assert r["npu_execution_measured"] is False


def test_inactive_or_missing_service_still_cannot_authorize_execution():
    val = good()
    val["geniex"] = {
        "service_mainpid_present": False,
        "geniex_process_count": 0,
        "fast_rpc_secure_fd_open": False,
    }
    r = gate.classify(**val)
    assert "exclusive_vendor_approved_htp_window_not_attested" in r["blockers"]
    assert r["geniex_concurrency_status"] == "no_go_geniex_service_state_unknown"
    assert r["htp_backend_initialization_succeeded"] is False


def test_geniex_idle_is_not_a_durable_quiescence_guarantee():
    val = good()
    val["geniex"]["fast_rpc_secure_fd_open"] = False
    r = gate.classify(**val)
    assert "no_go_geniex_active_concurrent_htp_unsafe" in r["blockers"]
    assert r["htp_per_operator_placement_verified"] is False


@pytest.mark.parametrize("drop,expected", [
    ("--profiling_level", "installed_netrun_basic_capture_flags_missing"),
    ("--backend", "installed_netrun_basic_capture_flags_missing"),
    ("--use_native_input_files", "installed_netrun_basic_capture_flags_missing"),
    ("--input_log", "installed_profile_viewer_reader_flags_missing"),
    ("--reader", "installed_profile_viewer_reader_flags_missing"),
])
def test_missing_required_cli_flags_fail_closed(drop, expected):
    val = good()
    key = "viewer_flags" if drop in gate.VIEWER_FLAGS else "netrun_flags"
    val[key] = val[key] - {drop}
    r = gate.classify(**val)
    assert expected in r["blockers"]
    assert r["npu_execution_measured"] is False


@pytest.mark.parametrize("value,field,reason", [
    (False, "skel", "packaged_v75_dsp_skel_missing"),
    ({}, "reader", "packaged_htp_profile_reader_missing"),
    ({}, "hostlibs", "packaged_htp_host_library_missing"),
    (None, "verified_fixture", "qnn_dlc_forward_format_unverified"),
    (True, "free_kib", "available_ram_below_threshold_or_unverified"),
    ("x86_64", "machine", "not_ventuno_arm64"),
])
def test_preconditions_missing_are_explicit_and_never_npu_proof(value, field, reason):
    val = good()
    val[field] = value
    report = gate.classify(**val)
    assert reason in report["blockers"]
    assert report["qnn_or_htp_executed"] is False


def test_sdk_pair_mismatch_prevents_forward_compatibility():
    val = good()
    val["packages"]["qairt-dsp-binaries"]["version"] = "2.45.0"
    r = gate.classify(**val)
    assert "installed_qairt_246_pair_unverified" in r["blockers"]
    assert "qnn_dlc_forward_format_unverified" in r["blockers"]


@pytest.mark.parametrize("owner,arch,regular", [
    ("unknown", "aarch64_elf_header", True),
    ("qairt-libs", "hexagon_elf_header", True),
    ("qairt-libs", "aarch64_elf_header", False),
])
def test_only_packaged_aarch64_reader_is_trusted(owner, arch, regular):
    def inspect(path, root):
        assert root == Path("/usr")
        assert path.name == "libQnnHtpProfilingReader.so"
        return {
            "path_inside_usr": True,
            "file_regular": regular,
            "header_class": arch,
            "package_owner": owner,
            "library_file_header_read": True,
        }
    inspected = gate.attest_packaged_htp_reader(inspect)
    assert inspected == {"usr_lib": False, "multiarch": False}


def test_valid_reader_is_evidence_of_reader_only_not_profile_capture():
    def inspect(path, root):
        return {
            "path_inside_usr": True,
            "file_regular": True,
            "header_class": "aarch64_elf_header",
            "package_owner": "qairt-libs",
            "library_file_header_read": True,
        }
    assert all(gate.attest_packaged_htp_reader(inspect).values())
    r = gate.classify(**good())
    assert r["vendor_htp_reader_executed"] is False
    assert r["cli_profile_capture_is_not_npu_proof"] is True


def test_private_extra_metadata_never_leaks_into_status():
    val = good()
    val["geniex"]["private_cache"] = "/home/arduino/SECRET/model"
    val["reader"]["SECRET_USER_ROOT"] = False
    val["packages"]["private"] = "TOKEN_ABC"
    report = json.dumps(gate.classify(**val))
    assert "SECRET" not in report
    assert "TOKEN" not in report
    assert "/home" not in report
    assert "qnn-profiling-data" not in report


def test_real_probe_only_calls_readonly_sources(monkeypatch):
    vals = good()
    invoked = []
    def wrap(key):
        def fake(*args):
            invoked.append(key)
            return vals[key]
        return fake
    monkeypatch.setattr(gate, "attest_packaged_htp_reader", wrap("reader"))
    monkeypatch.setattr(gate, "package_versions", wrap("packages"))
    monkeypatch.setattr(gate, "verify_fixture", wrap("verified_fixture"))
    monkeypatch.setattr(gate, "_find_libraries", wrap("hostlibs"))
    monkeypatch.setattr(gate, "_find_v75_skel_directory", lambda: Path("/usr/lib/dsp/cdsp"))
    monkeypatch.setattr(gate, "main_pid_from_systemd", lambda: 101)
    monkeypatch.setattr(gate, "summarize_service", lambda *a: vals["geniex"])
    monkeypatch.setattr(gate, "available_memory_kib", wrap("free_kib"))
    monkeypatch.setattr(gate.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(gate.shutil, "which", lambda name: "/usr/bin/" + name)
    monkeypatch.setattr(gate, "_help_flags", lambda p: (
        vals["netrun_flags"] if p.endswith("qnn-net-run") else vals["viewer_flags"]
    ))
    report = gate.report()
    assert report["packaged_htp_reader_found"] is True
    assert report["netrun_basic_capture_cli_supported"] is True
    assert report["qnn_or_htp_executed"] is False
    assert set(invoked) >= {"reader", "packages", "verified_fixture", "hostlibs", "free_kib"}
