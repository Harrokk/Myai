"""Fake-only tests for one bounded inference on the existing GenieX service.

No network requests, real process checks, hardware access or system changes.
"""
from contextlib import contextmanager
import json
import pytest

from scripts import ventuno_existing_geniex_synthetic_once as probe

MODEL = "qualcomm/Qwen3-4B-Instruct-2507:W4A16"


def evidence():
    return {
        "service_mainpid_present": True,
        "geniex_process_count": 1,
        "complete_fast_rpc_fd_scan": True,
        "complete_process_maps": True,
        "runtime_backend_evidence": True,
        "fast_rpc_secure_fd_open": True,
        "mapped_libraries": {"libQnnHtp.so": True},
        "status": "backend-associated-with-service",
    }


def setup_success(monkeypatch, *, post=None, second_pid=555, second_evidence=None):
    monkeypatch.setenv("MYAI_ALLOW_EXISTING_GENIEX_SYNTHETIC_ONCE", "yes")
    pid_calls = []
    def fake_pid():
        pid_calls.append(True)
        return 555 if len(pid_calls) < 3 else second_pid
    monkeypatch.setattr(probe, "main_pid_from_systemd", fake_pid)
    summaries = []
    def fake_summary(*args):
        summaries.append(True)
        return evidence() if len(summaries) == 1 else (
            evidence() if second_evidence is None else second_evidence
        )
    monkeypatch.setattr(probe, "summarize_service", fake_summary)
    monkeypatch.setattr(probe.single, "available_memory_kib", lambda: 12 * 1048576)

    models_calls = []
    class Response:
        def __enter__(self):
            models_calls.append(True)
            return self
        def __exit__(self, *args):
            return False
    def fake_open(url, *, timeout):
        assert url == "http://127.0.0.1:18181/v1/models"
        assert timeout == 5
        return Response()
    monkeypatch.setattr(probe.single, "urlopen", fake_open)
    monkeypatch.setattr(probe.single, "_read_json",
                        lambda response: {"data": [{"id": MODEL}]})
    post_calls = []
    def fake_post(model):
        post_calls.append(model)
        if post:
            return post(model)
        return {"response_nonempty": True, "returned_text_logged": False,
                "wall_seconds": 0.2, "completion_tokens": 2}
    monkeypatch.setattr(probe.single, "run_one_synthetic_request", fake_post)
    return pid_calls, summaries, models_calls, post_calls


def test_unapproved_request_never_even_reads_service(monkeypatch):
    monkeypatch.delenv("MYAI_ALLOW_EXISTING_GENIEX_SYNTHETIC_ONCE", raising=False)
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: pytest.fail(
        "Did not opt in to any service check"))
    result = probe.attempt()
    assert result["status"] == "no_go_not_authorized"
    assert result["http_post_performed"] is False


@pytest.mark.parametrize("bad", [
    {"complete_fast_rpc_fd_scan": False},
    {"complete_process_maps": False},
    {"geniex_process_count": 2},
    {"geniex_process_count": True},
    {"runtime_backend_evidence": False},
    {"fast_rpc_secure_fd_open": False},
    {"mapped_libraries": {"libQnnHtp.so": False}},
    {"status": "inconclusive-backend-association"},
    {"service_mainpid_present": False},
])
def test_incomplete_process_or_dsp_state_never_posts(bad, monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    monkeypatch.setattr(probe, "summarize_service",
                        lambda *args: {**evidence(), **bad})
    result = probe.attempt()
    assert result["status"] == "no_go_existing_geniex_backend_unverified"
    assert posts == models == []
    assert result["http_post_performed"] is False
    assert result["secondary_qnn_htp_client_started"] is False


def test_low_memory_blocks_preexisting_service_prompt(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    monkeypatch.setattr(probe.single, "available_memory_kib", lambda: 1)
    result = probe.attempt()
    assert result["status"] == "no_go_existing_backend_or_ram_unverified"
    assert models == posts == []


def test_no_systemd_service_never_requests_model_list(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: None)
    result = probe.attempt()
    assert result["status"] == "no_go_existing_geniex_backend_unverified"
    assert models == posts == []


def test_valid_single_inference_still_does_not_claim_htp_placement(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    result = probe.attempt()
    assert result["status"] == "existing_geniex_responded_htp_placement_unverified"
    assert len(models) == 1
    assert posts == [MODEL]
    assert len(reports) == 2
    assert result["same_existing_service_mainpid_after_post"] is True
    assert result["existing_backend_attested_after_post"] is True
    assert result["http_post_performed"] is True
    assert result["synthetic_response_received"] is True
    assert result["sample"]["returned_text_logged"] is False
    assert result["htp_operator_placement_verified"] is False
    assert result["htp_accelerator_utilization_measured"] is False
    assert result["secondary_qnn_htp_client_started"] is False
    assert result["model_started_or_reloaded"] is False
    assert result["existing_service_or_permissions_modified"] is False
    assert MODEL not in json.dumps(result)


def test_service_restarts_between_metadata_and_post_blocks(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    # Two calls: preview and just-before-request guard.
    monkeypatch.setattr(probe, "main_pid_from_systemd",
                        iter((555, 999)).__next__)
    result = probe.attempt()
    assert result["status"] == "no_go_geniex_restarted_during_preflight"
    assert posts == []


def test_service_restarted_after_post_does_not_report_stable_backend(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch, second_pid=777)
    result = probe.attempt()
    assert posts == [MODEL]
    assert result["status"] == (
        "existing_geniex_response_but_backend_afterward_unverified")
    assert result["existing_backend_attested_after_post"] is False
    assert result["same_existing_service_mainpid_after_post"] is False
    assert result["npu_per_op_profile_measured"] is False


def test_missing_backend_after_post_cannot_be_attested(monkeypatch):
    bad = {**evidence(), "fast_rpc_secure_fd_open": False}
    ids, reports, models, posts = setup_success(
        monkeypatch, second_evidence=bad)
    result = probe.attempt()
    assert posts == [MODEL]
    assert result["existing_backend_attested_after_post"] is False
    assert result["status"] == (
        "existing_geniex_response_but_backend_afterward_unverified")


def test_fail_closed_on_unexpected_model(monkeypatch):
    ids, reports, models, posts = setup_success(monkeypatch)
    monkeypatch.setattr(probe.single, "_read_json", lambda _: {
        "data": [{"id": "not-the-pinned-model"}]})
    result = probe.attempt()
    assert result["status"] == "no_go_unexpected_existing_model"
    assert posts == []


def test_private_exception_data_never_escapes(monkeypatch):
    def raise_secret(model):
        raise RuntimeError("SECRET_KEY at /private/model-cache")
    ids, reports, models, posts = setup_success(monkeypatch, post=raise_secret)
    result = probe.attempt()
    encoded = json.dumps(result)
    assert result["status"] == "existing_geniex_request_or_attestation_failed"
    assert result["synthetic_response_received"] is False
    assert result["sample"] is None
    assert "SECRET_KEY" not in encoded
    assert "/private/" not in encoded


def test_success_is_not_truth_about_vendor_operator_support(monkeypatch):
    setup_success(monkeypatch)
    result = probe.attempt()
    assert result["npu_per_op_profile_measured"] is False
    assert result["htp_operator_placement_verified"] is False
    assert result["htp_accelerator_utilization_measured"] is False
    assert result["user_content_read_or_logged"] is False
    assert result["actual_response_text_logged"] is False
