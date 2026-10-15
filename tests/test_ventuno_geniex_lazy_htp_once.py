"""Mock-only fail-closed safety gate for a single existing GenieX NPU query."""
import json
from types import SimpleNamespace
from urllib.request import Request

import pytest
from scripts import ventuno_geniex_lazy_htp_once as probe

MODEL = "qualcomm/Qwen3-4B-Instruct-2507:W4A16"


def idle():
    return {
        "status": "inconclusive-backend-association",
        "service_mainpid_present": True,
        "geniex_process_count": 1,
        "complete_process_maps": True,
        "complete_fast_rpc_fd_scan": True,
        "mapped_libraries": {"libQnnHtp.so": False},
        "fast_rpc_secure_fd_open": False,
        "runtime_backend_evidence": False,
    }


def activated():
    result = idle()
    result.update(
        status="backend-associated-with-service",
        mapped_libraries={"libQnnHtp.so": True},
        fast_rpc_secure_fd_open=True,
        runtime_backend_evidence=True,
    )
    return result


def ready(monkeypatch, *, snapshots=None, reported_model=True,
          startup=None, ram=8 * 1048576, installed=True,
          sample=None):
    monkeypatch.setenv("MYAI_ALLOW_ONE_EXISTING_GENIEX_LAZY_HTP_REQUEST", "yes")
    replies = iter(snapshots or [(111, idle()), (111, idle()), (111, activated())])
    monkeypatch.setattr(probe, "_snapshot", lambda: next(replies))
    monkeypatch.setattr(probe, "service_startup_hint", lambda: (
        {
            "direct_geniex_serve_declared": True,
            "declared_compute_hint": "npu_requested_not_verified",
            "qairt_override_option_declared": False,
        } if startup is None else startup
    ))
    monkeypatch.setattr(probe, "_package_pair_verified", lambda: installed)
    monkeypatch.setattr(probe.single, "available_memory_kib", lambda: ram)
    lookups = []
    monkeypatch.setattr(probe, "_existing_model",
                        lambda: lookups.append(True) or reported_model)
    sends = []
    def post(model_id):
        sends.append(model_id)
        if isinstance(sample, Exception):
            raise sample
        return sample if sample is not None else {
            "response_nonempty": True,
            "returned_text_logged": False,
            "wall_seconds": 0.25,
            "completion_tokens": 2,
        }
    monkeypatch.setattr(probe, "_post_once", post)
    return sends, lookups


def test_successful_existing_model_request_with_backend_association_not_operator_proof(monkeypatch):
    sends, lookups = ready(monkeypatch)
    r = probe.attempt()
    assert sends == [MODEL] and lookups == [True]
    assert r["http_post_attempted"] is True
    assert r["bounded_synthetic_reply_received"] is True
    assert r["existing_backend_associated_after_post"] is True
    assert r["status"] == "existing_geniex_synthetic_reply_and_htp_association_only"
    assert r["same_service_mainpid_before_post"] is True
    assert r["same_service_mainpid_after_post"] is True
    assert r["sample"]["returned_text_logged"] is False
    assert r["npu_operator_placement_verified"] is False
    assert r["htp_cycles_or_utilization_measured"] is False
    assert r["new_htp_or_geniex_process_started"] is False
    assert r["service_or_model_configuration_modified"] is False
    assert r["model_response_text_exported"] is False
    assert MODEL not in json.dumps(r)


def test_opt_in_missing_prevents_even_probes(monkeypatch):
    monkeypatch.delenv("MYAI_ALLOW_ONE_EXISTING_GENIEX_LAZY_HTP_REQUEST",
                        raising=False)
    monkeypatch.setattr(probe, "_snapshot",
                        lambda: pytest.fail("unauthorized scan"))
    assert probe.attempt()["status"] == "no_go_explicit_opt_in_missing"


@pytest.mark.parametrize("change", [
    {"geniex_process_count": 2},
    {"geniex_process_count": True},
    {"complete_process_maps": False},
    {"complete_fast_rpc_fd_scan": False},
    {"service_mainpid_present": False},
    {"mapped_libraries": {"libQnnHtp.so": True}},
    {"fast_rpc_secure_fd_open": True},
    {"status": "backend-associated-with-service"},
])
def test_worker_not_safely_idle_prevents_model_request(monkeypatch, change):
    report = {**idle(), **change}
    sends, lookups = ready(monkeypatch, snapshots=[(111, report)])
    r = probe.attempt()
    assert r["status"] == "no_go_existing_worker_not_confidently_idle"
    assert sends == lookups == []


@pytest.mark.parametrize("startup", [
    {"direct_geniex_serve_declared": False,
     "declared_compute_hint": "npu_requested_not_verified",
     "qairt_override_option_declared": False},
    {"direct_geniex_serve_declared": True,
     "declared_compute_hint": "cpu_requested_not_verified",
     "qairt_override_option_declared": False},
    {"direct_geniex_serve_declared": True,
     "declared_compute_hint": "npu_requested_not_verified",
     "qairt_override_option_declared": True},
    {},
])
def test_startup_command_not_verified_prevents_inference(monkeypatch, startup):
    sends, lookups = ready(monkeypatch, startup=startup)
    r = probe.attempt()
    assert r["status"] == "no_go_declared_npu_service_config_unverified"
    assert sends == lookups == []


def test_incompatible_vendor_runtime_pair_blocks_before_get(monkeypatch):
    sends, lookups = ready(monkeypatch, installed=False)
    r = probe.attempt()
    assert r["status"] == "no_go_installed_qairt_runtime_pair_unverified"
    assert not sends and not lookups


@pytest.mark.parametrize("memory", [None, 0, 4 * 1048576, "8GiB", True])
def test_low_or_unknown_available_ram_blocks_post(monkeypatch, memory):
    sends, lookups = ready(monkeypatch, ram=memory)
    r = probe.attempt()
    assert r["status"] == "no_go_insufficient_available_memory"
    assert not sends and not lookups


def test_mismatched_model_catalog_blocks_post(monkeypatch):
    sends, lookups = ready(monkeypatch, reported_model=False)
    r = probe.attempt()
    assert r["status"] == "no_go_exact_model_catalog_unverified"
    assert sends == [] and lookups == [True]


def test_process_changed_just_before_post_is_not_allowed(monkeypatch):
    sends, lookups = ready(monkeypatch, snapshots=[
        (111, idle()), (222, idle()),
    ])
    r = probe.attempt()
    assert r["status"] == "no_go_worker_changed_before_inference"
    assert sends == [] and lookups == [True]


def test_process_replaced_after_post_does_not_attest_backend(monkeypatch):
    sends, _ = ready(monkeypatch, snapshots=[
        (111, idle()), (111, idle()), (222, activated()),
    ])
    r = probe.attempt()
    assert sends == [MODEL]
    assert r["same_service_mainpid_after_post"] is False
    assert r["existing_backend_associated_after_post"] is False
    assert r["status"] == "existing_geniex_synthetic_reply_without_htp_association"


def test_idling_backend_remains_unobserved_after_success(monkeypatch):
    sends, _ = ready(monkeypatch, snapshots=[
        (111, idle()), (111, idle()), (111, idle()),
    ])
    r = probe.attempt()
    assert sends == [MODEL]
    assert r["status"] == "existing_geniex_synthetic_reply_without_htp_association"
    assert r["npu_operator_placement_verified"] is False


def test_failed_post_does_not_escape_private_error(monkeypatch):
    sends, _ = ready(monkeypatch, sample=RuntimeError(
        "PRIVATE_TOKEN at /home/private/cache"))
    r = probe.attempt()
    assert sends == [MODEL]
    assert r["status"] == "synthetic_request_failed_sanitized"
    assert r["bounded_synthetic_reply_received"] is False
    assert "PRIVATE_TOKEN" not in json.dumps(r)
    assert "/home/private" not in json.dumps(r)
    assert r["sample"] is None


def test_invalid_onnx_model_id_not_sent_via_post(monkeypatch):
    with pytest.raises(ValueError):
        probe._post_once("some/other-model")


def test_get_exact_model_fails_closed_on_other_model(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def geturl(self):
            return probe.single.BASE_URL + "/models"
        def read(self, n):
            return json.dumps({"data": [{"id":
                "qualcomm/Qwen3-8B-Instruct-2507:W4A16"}]}).encode()
    monkeypatch.setattr("urllib.request.build_opener",
                        lambda *args: SimpleNamespace(
                            open=lambda *a, **kw: Response()))
    assert probe._existing_model() is False


def test_post_exactly_one_local_prompt_no_proxy_redirect_and_no_output_text(monkeypatch):
    class Response:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def geturl(self):
            return probe.single.BASE_URL + "/chat/completions"
        def read(self, n):
            return json.dumps({
                "choices": [{"message": {"content": "SECRET_USER_DATA"}}],
                "usage": {"completion_tokens": 3, "prompt_tokens": 9},
                "timings": {"predicted_per_second": 11},
            }).encode()
    calls = []
    def fake_build(*handlers):
        assert any(isinstance(x, probe.ProxyHandler) for x in handlers)
        assert any(isinstance(x, probe._NoRedirects) for x in handlers)
        def open_one(request, timeout):
            assert request.get_method() == "POST"
            assert request.full_url == probe.single.BASE_URL + "/chat/completions"
            assert timeout == 30
            body = json.loads(request.data)
            assert body["model"] == MODEL
            assert body["max_tokens"] == 24
            assert body["stream"] is False
            assert body["messages"] == [{
                "role": "user", "content": "Compute 7 + 5. Reply only with the integer result."
            }]
            calls.append(True)
            return Response()
        return SimpleNamespace(open=open_one)
    monkeypatch.setattr(probe, "build_opener", fake_build)
    sample = probe._post_once(MODEL)
    assert len(calls) == 1
    assert sample["response_nonempty"] is True
    assert sample["returned_text_logged"] is False
    assert "SECRET_USER_DATA" not in json.dumps(sample)
