"""Fake-only read-only GenieX NPU backend diagnostic tests."""
import json
import pytest
from scripts import ventuno_existing_geniex_npu_backend_reasons_readonly as probe


def good():
    return {
        "service_mainpid_present": True,
        "geniex_process_count": 1,
        "complete_process_maps": True,
        "complete_fast_rpc_fd_scan": True,
        "mapped_libraries": {
            "libQnnHtp.so": True,
            "libQnnHtpV75Stub.so": True,
        },
        "fast_rpc_secure_fd_open": True,
        "runtime_backend_evidence": True,
        "status": "backend-associated-with-service",
    }


def test_complete_process_association_is_not_proof_of_placement():
    r = probe.classify(good(), 5 * 1048576)
    assert r["status"] == (
        "existing_backend_association_observed_not_htp_execution_proof"
    )
    assert r["backend_association_confirmed"] is True
    assert r["actual_htp_npu_execution_proven"] is False
    assert r["graph_operator_placement_measured"] is False
    assert r["synthetic_prompt_posted"] is False
    assert r["device_opened"] is False


@pytest.mark.parametrize("field,value,reason", [
    ("service_mainpid_present", False, "geniex_service_mainpid_not_verified"),
    ("geniex_process_count", 2, "exactly_one_geniex_process_not_verified"),
    ("geniex_process_count", True, "exactly_one_geniex_process_not_verified"),
    ("complete_process_maps", False, "complete_geniex_maps_not_verified"),
    ("complete_fast_rpc_fd_scan", False, "complete_geniex_fd_scan_not_verified"),
    ("fast_rpc_secure_fd_open", False,
     "geniex_secure_fastrpc_descriptor_not_observed"),
])
def test_missing_service_backend_evidence_is_explicit(field, value, reason):
    sample = {**good(), field: value}
    r = probe.classify(sample, 8 * 1048576)
    assert r["status"] == "no_go_existing_backend_association_inconclusive"
    assert reason in r["observations"]
    assert r["backend_association_confirmed"] is False


def test_htp_library_not_seen_is_not_called_proven_cpu_fallback():
    sample = good()
    sample["mapped_libraries"] = {"libQnnHtp.so": False}
    r = probe.classify(sample, 8 * 1048576)
    assert "geniex_htp_library_mapping_not_observed" in r["observations"]
    assert r["actual_htp_npu_execution_proven"] is False
    assert "cpu_fallback" not in json.dumps(r)


def test_v75_stub_not_seen_does_not_by_itself_block_association():
    sample = good()
    sample["mapped_libraries"]["libQnnHtpV75Stub.so"] = False
    r = probe.classify(sample, 8 * 1048576)
    assert r["backend_association_confirmed"] is True
    assert r["geniex_htp_v75_stub_mapped"] is False


def test_contract_mismatch_is_a_distinct_blocker():
    sample = {**good(), "runtime_backend_evidence": False}
    r = probe.classify(sample, 8 * 1048576)
    assert r["observations"] == ["attestation_contract_not_fully_satisfied"]
    assert r["backend_association_confirmed"] is False


@pytest.mark.parametrize("memory", [None, 0, 2000, "secret", True])
def test_insufficient_or_malformed_memory_is_no_go(memory):
    r = probe.classify(good(), memory)
    assert "available_memory_threshold_not_met_or_unknown" in r["observations"]
    assert r["backend_association_confirmed"] is False


def test_missing_snapshot_is_no_go_and_no_sensitive_details():
    result = probe.classify(None, None)
    assert result["status"] == "no_go_existing_backend_association_inconclusive"
    assert result["synthetic_prompt_posted"] is False
    assert result["model_or_service_modified"] is False
    assert "home/" not in json.dumps(result)


def test_report_reads_only_existing_preapproved_metadata(monkeypatch):
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: 99)
    monkeypatch.setattr(probe, "summarize_service",
                        lambda *args: good())
    monkeypatch.setattr(probe, "available_memory_kib",
                        lambda: 5 * 1048576)
    result = probe.report()
    assert result["backend_association_confirmed"] is True
    assert "99" not in json.dumps(result)
    assert result["qnn_backend_executed"] is False


def test_unknown_mainpid_skips_process_files(monkeypatch):
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: None)
    monkeypatch.setattr(probe, "summarize_service",
                        lambda *args: pytest.fail("No PID: no /proc scan"))
    monkeypatch.setattr(probe, "available_memory_kib",
                        lambda: 5 * 1048576)
    assert probe.report()["backend_association_confirmed"] is False
