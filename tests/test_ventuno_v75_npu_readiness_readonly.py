"""No hardware is accessed: synthetic evidence for V75 NPU preflight."""
import json

import pytest

from scripts import ventuno_v75_npu_readiness_readonly as probe


def good():
    return dict(
        packages={
            "qairt-libs": {"status": "installed", "version": "2.46.0-0ubuntu1"},
            "qairt-dsp-binaries": {
                "status": "installed", "version": "2.46.0-0ubuntu1",
            },
        },
        libraries={name: object() for name in probe.LIBS},
        skel_present=True,
        service={
            "service_mainpid_present": True,
            "geniex_process_count": 1,
            "complete_fast_rpc_fd_scan": True,
            "complete_process_maps": True,
            "fast_rpc_secure_fd_open": False,
        },
        available_kib=12 * 1048576,
        fixture={"file_identity_verified": True},
        policy={"nodes": {"cdsp_secure": {
            "character_device": True,
            "runner_effective_read_access": True,
            "runner_effective_write_access": True,
        }}},
        machine="aarch64",
    )


def test_even_all_good_metadata_cannot_authorize_second_live_htp():
    report = probe.evaluate(**good())
    assert report["status"] == "no_go"
    assert report["geniex_fastrpc_state"] == (
        "no_go_geniex_active_concurrent_htp_unsafe"
    )
    assert "matching_246_htp_artifact_not_attested" in report["blockers"]
    assert "active_geniex_concurrency_unsafe" in report["blockers"]
    assert report["npu_inference_verified"] is False
    assert report["qnn_or_htp_attempted"] is False
    assert report["npu_operator_placement_measured"] is False
    assert report["service_or_packages_modified"] is False


def test_live_secure_fastrpc_descriptor_blocks_independently():
    values = good()
    values["service"]["fast_rpc_secure_fd_open"] = True
    report = probe.evaluate(**values)
    assert "existing_geniex_fastrpc_busy" in report["blockers"]
    assert report["status"] == "no_go"


@pytest.mark.parametrize("service", [
    {}, None, {"fast_rpc_secure_fd_open": False},
    {"complete_fast_rpc_fd_scan": False, "fast_rpc_secure_fd_open": False},
])
def test_unknown_service_never_claims_exclusive_quiescence(service):
    values = good()
    values["service"] = service
    report = probe.evaluate(**values)
    assert "exclusive_htp_maintenance_not_attested" in report["blockers"]
    assert report["exclusive_htp_execution_attested"] is False


@pytest.mark.parametrize("runtime_version", [
    "2.45.0", "2.47.0", None, "SECRET_LOCAL_PATH", "2.46",
])
def test_other_or_malformed_runtime_versions_refuse_go(runtime_version):
    values = good()
    values["packages"]["qairt-libs"]["version"] = runtime_version
    report = probe.evaluate(**values)
    assert report["runtime_both_qairstack_246"] is False
    assert "qairt_246_runtime_pair_unverified" in report["blockers"]


def test_partial_library_skel_and_bad_fastrpc_metadata_all_no_go():
    values = good()
    values["libraries"] = {"libQnnHtp.so": object()}
    values["skel_present"] = False
    values["policy"] = {"nodes": {"cdsp_secure": {"character_device": True}}}
    report = probe.evaluate(**values)
    assert "packaged_htp_host_libraries_unverified" in report["blockers"]
    assert "packaged_v75_dsp_skel_unverified" in report["blockers"]
    assert "runner_fastrpc_device_access_unverified" in report["blockers"]


def test_unverified_dlc_and_ram_remain_no_go():
    values = good()
    values["available_kib"] = None
    values["fixture"] = {"file_identity_verified": False}
    report = probe.evaluate(**values)
    assert "existing_245_fixture_integrity_unverified" in report["blockers"]
    assert "available_ram_below_safe_threshold_or_unknown" in report["blockers"]


def test_wrong_architecture_and_malformed_inputs_fail_closed():
    values = good()
    values.update(machine="x86_64", packages=None, libraries=None,
                  fixture=None, policy=None, service=None)
    report = probe.evaluate(**values)
    assert report["status"] == "no_go"
    assert "not_aarch64_target" in report["blockers"]
    assert report["npu_inference_verified"] is False


def test_real_probe_uses_only_bounded_readonly_helpers(monkeypatch):
    values = good()
    monkeypatch.setattr(probe, "package_versions", lambda: values["packages"])
    monkeypatch.setattr(probe, "_find_libraries", lambda: values["libraries"])
    monkeypatch.setattr(probe, "_find_v75_skel_directory",
                        lambda: "/not/exported")
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: 4321)
    monkeypatch.setattr(probe, "summarize_service",
                        lambda *args: values["service"])
    monkeypatch.setattr(probe, "available_memory_kib",
                        lambda: values["available_kib"])
    monkeypatch.setattr(probe, "verify_fixture",
                        lambda *_: values["fixture"])
    monkeypatch.setattr(probe, "policy_report", lambda: values["policy"])
    monkeypatch.setattr(probe.platform, "machine", lambda: "aarch64")
    result = probe.report()
    encoded = json.dumps(result, sort_keys=True)
    assert result["status"] == "no_go"
    assert "/not/exported" not in encoded
    assert "4321" not in encoded
    assert "package_version" not in encoded
    assert result["private_paths_or_vendor_logs_emitted"] is False
    assert result["devices_opened"] is False


def test_no_fields_claim_runtime_htp_activation_or_vendor_certification():
    result = probe.evaluate(**good())
    assert not any(x is True for x in [
        result["qnn_or_htp_attempted"],
        result["npu_inference_verified"],
        result["npu_operator_placement_measured"],
        result["exclusive_htp_execution_attested"],
        result["matching_246_htp_artifact_attested"],
    ])
