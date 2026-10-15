"""All tests simulate /proc, systemctl and HTTP; no real service is touched."""
import json
from types import SimpleNamespace
from urllib.request import Request

import pytest

from scripts import ventuno_geniex_idle_model_readonly as probe


MODELS = "expected_single_qairt_model_listed_not_execution_proof"


def evidence(*, backend=False):
    return {
        "service_mainpid_present": True,
        "geniex_process_count": 1,
        "complete_process_maps": True,
        "complete_fast_rpc_fd_scan": True,
        "mapped_libraries": {
            "libQnnHtp.so": backend,
            "libQnnHtpV75Stub.so": backend,
        },
        "fast_rpc_secure_fd_open": backend,
        "runtime_backend_evidence": backend,
        "status": (
            "backend-associated-with-service" if backend
            else "inconclusive-backend-association"
        ),
    }


def setup(monkeypatch, *, before=False, after=False, model=MODELS,
          start_pid=111, end_pid=111):
    monkeypatch.setattr(probe, "service_startup_hint", lambda: probe.startup_hint(
        "{ path=/usr/bin/geniex ; argv[]=/usr/bin/geniex serve --compute npu ; ignore_errors=no }"
    ))
    pids = iter((start_pid, end_pid))
    monkeypatch.setattr(probe, "main_pid_from_systemd", lambda: next(pids))
    observations = iter((evidence(backend=before), evidence(backend=after)))
    monkeypatch.setattr(probe, "summarize_service", lambda *args: next(observations))
    monkeypatch.setattr(probe, "available_memory_kib",
                        lambda: 7 * 1048576)
    monkeypatch.setattr(probe, "fixed_loopback_catalog", lambda: model)


def test_catalog_present_without_mapped_htp_is_not_cpu_or_npu_proof(monkeypatch):
    setup(monkeypatch)
    r = probe.report()
    assert r["status"] == "catalog_present_backend_not_observed_possible_idle_state"
    assert r["startup"]["declared_compute_hint"] == "npu_requested_not_verified"
    assert r["model_catalog"] == MODELS
    assert r["backend_before_get"]["backend_association_confirmed"] is False
    assert r["backend_after_get"]["backend_association_confirmed"] is False
    assert r["same_geniex_mainpid_across_get"] is True
    assert r["http_post_performed"] is False
    assert r["model_inference_executed"] is False
    assert r["htp_graph_placement_verified"] is False
    assert r["npu_utilization_measured"] is False
    assert r["second_qnn_htp_client_started"] is False
    assert r["model_service_or_permissions_modified"] is False
    assert "cpu_fallback" not in json.dumps(r)


def test_get_with_backend_already_active_is_still_not_profiling(monkeypatch):
    setup(monkeypatch, before=True, after=True)
    r = probe.report()
    assert r["status"] == "existing_backend_association_only_not_htp_proof"
    assert r["backend_before_get"]["backend_association_confirmed"] is True
    assert r["htp_graph_placement_verified"] is False


def test_new_mapping_after_catalog_get_not_interpreted_as_inference(monkeypatch):
    setup(monkeypatch, before=False, after=True)
    r = probe.report()
    assert r["status"] == "backend_association_newly_observed_no_htp_proof"
    assert r["model_inference_executed"] is False


def test_mainpid_changed_is_no_go_regardless_of_model_listing(monkeypatch):
    setup(monkeypatch, before=True, after=True, end_pid=222)
    r = probe.report()
    assert r["status"] == "no_go_service_identity_unverified_or_changed"
    assert r["same_geniex_mainpid_across_get"] is False


def test_missing_known_model_is_no_go_not_evidence_of_cpu_fallback(monkeypatch):
    setup(monkeypatch, before=True, after=True,
          model="no_expected_single_qairt_model_in_catalog")
    r = probe.report()
    assert r["status"] == "no_go_pinned_model_catalog_unverified"


def test_unit_direct_geniex_npu_mode_only_declaration_not_runtime():
    secret = "SECRET_ARG=/private/user/cache"
    p = probe.startup_hint(
        "{ path=/home/a/bin/geniex ; argv[]=/home/a/bin/geniex serve "
        "--compute=npu --qairt-lib /private/qairt " + secret +
        " ; start_time=[hidden] }"
    )
    assert p["direct_geniex_serve_declared"] is True
    assert p["declared_compute_hint"] == "npu_requested_not_verified"
    assert p["qairt_override_option_declared"] is True
    assert p["unit_command_inspection"] == "direct_geniex_serve_declared"
    assert p["unit_environment_inspected"] is False
    assert "SECRET" not in json.dumps(p)
    assert "/private/" not in json.dumps(p)


@pytest.mark.parametrize("raw", [
    None, "", "invalid", "argv[]=geniex serve\nargv[]=geniex serve",
    "{ path=/usr/bin/bash ; argv[]=/usr/bin/bash start_geniex.sh; }",
    "X" * (probe.MAX_UNIT_BYTES + 1),
])
def test_missing_indirect_or_oversized_unit_exec_not_trusted(raw):
    p = probe.startup_hint(raw)
    assert p["direct_geniex_serve_declared"] is False
    assert p["declared_compute_hint"] == "unknown"
    assert p["unit_arguments_exported"] is False


@pytest.mark.parametrize("args,expect", [
    ("", "not_explicitly_selected"),
    (" --compute npu", "npu_requested_not_verified"),
    (" --compute=cpu", "cpu_requested_not_verified"),
    (" --compute unknown", "other_or_ambiguous"),
    (" --compute gpu --compute npu", "other_or_ambiguous"),
])
def test_compute_flag_never_asserts_accelerator_activated(args, expect):
    p = probe.startup_hint(
        "{ path=/usr/bin/geniex ; argv[]=/usr/bin/geniex serve" +
        args + " ; ignore_errors=no }"
    )
    assert p["declared_compute_hint"] == expect


def test_service_systemctl_output_is_inspected_only_in_memory(monkeypatch):
    def fake_run(args, **kwargs):
        assert tuple(args) == probe.UNIT_ARG
        assert kwargs["timeout"] == 5
        return SimpleNamespace(returncode=0, stdout=(
            b"{ path=/usr/bin/geniex ; argv[]=/usr/bin/geniex serve --compute=npu ; }"
        ))
    monkeypatch.setattr(probe.subprocess, "run", fake_run)
    p = probe.service_startup_hint()
    assert p["declared_compute_hint"] == "npu_requested_not_verified"
    assert "argv" not in json.dumps(p)


def test_no_proxy_no_redirect_get_and_strict_response_redaction(monkeypatch):
    captured = []
    class LocalResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def geturl(self):
            return probe.BASE_URL + "/models"
        def read(self, count):
            return json.dumps({"data": [{
                "id": "qualcomm/Qwen3-4B-Instruct-2507:W4A16",
                "private_extra": "SECRET_API_REPLY",
            }]}).encode()
    class Opener:
        def open(self, request, timeout):
            assert request.get_method() == "GET"
            assert request.full_url == probe.BASE_URL + "/models"
            assert timeout == 5
            return LocalResponse()
    def build(*args):
        assert any(isinstance(v, probe.ProxyHandler) for v in args)
        assert any(isinstance(v, probe._NoRedirects) for v in args)
        captured.append(True)
        return Opener()
    monkeypatch.setattr(probe, "build_opener", build)
    result = probe.fixed_loopback_catalog()
    assert result == MODELS
    assert captured and "SECRET" not in json.dumps(result)


def test_cross_host_redirect_is_rejected_before_network_follow():
    h = probe._NoRedirects()
    assert h.redirect_request(
        Request(probe.BASE_URL + "/models", method="GET"),
        None, 302, "Found", {},
        "https://third-party.invalid/private/credentials",
    ) is None


def test_nonlocal_response_url_is_not_read(monkeypatch):
    class BadResponse:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            return False
        def geturl(self):
            return "http://192.168.1.1/v1/models"
        def read(self, *args):
            pytest.fail("Untrusted remote body should never be read")
    monkeypatch.setattr(probe, "build_opener",
                        lambda *args: SimpleNamespace(open=lambda *a, **kw: BadResponse()))
    assert probe.fixed_loopback_catalog() == "unavailable_or_unverified"
