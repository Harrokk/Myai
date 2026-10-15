"""One opt-in bounded model request on the EXISTING idle GenieX NPU service.

The read-only 2026-10-15 physical-board probe established:
* geniex serve --compute npu, exact expected Qwen3 W4A16 in /v1/models,
* one stable GenieX PID with complete /proc maps and FD scans,
* no HTP library/secure FastRPC FD observed while idle.

QNN HTP may be initialized lazily at the first inference. To test
that possibility, execute AT MOST ONE fixed synthetic request through
the existing localhost server. Never spawn qnn-net-run, load a second
GenieX service, change service settings or inspect private model files.
A mapped library/FD after completion is an association, NOT direct HTP
cycle/utilization or operator-placement proof.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import ventuno_live_qairt_synthetic_once as single
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_geniex_idle_model_readonly import (
    fixed_loopback_catalog, service_startup_hint,
)
from scripts.ventuno_qairt_v75_package_readonly import package_versions
from scripts.ventuno_v75_npu_readiness_readonly import _installed_minor

EXPECTED_MODEL = "qualcomm/Qwen3-4B-Instruct-2507:W4A16"
MIN_AVAILABLE_KIB = 5 * 1048576


def _snapshot():
    pid = main_pid_from_systemd()
    if type(pid) is not int or pid <= 1:
        return None, {}
    return pid, summarize_service(Path("/proc"), pid)


def _idle_for_one_request(evidence):
    """Disallow an extra request unless we observed a single idle worker."""
    if not isinstance(evidence, dict):
        return False
    libs = evidence.get("mapped_libraries", {})
    return (
        evidence.get("status") == "inconclusive-backend-association"
        and evidence.get("service_mainpid_present") is True
        and type(evidence.get("geniex_process_count")) is int
        and evidence["geniex_process_count"] == 1
        and evidence.get("complete_process_maps") is True
        and evidence.get("complete_fast_rpc_fd_scan") is True
        and isinstance(libs, dict)
        and libs.get("libQnnHtp.so") is False
        and evidence.get("fast_rpc_secure_fd_open") is False
    )


def _package_pair_verified():
    version = package_versions()
    return (
        isinstance(version, dict)
        and _installed_minor(version.get("qairt-libs")) == "2.46"
        and _installed_minor(version.get("qairt-dsp-binaries")) == "2.46"
    )


def _existing_model():
    """One pinned GET and an in-memory exact model-ID comparison only."""
    from urllib.request import ProxyHandler, Request, build_opener
    from scripts.ventuno_geniex_idle_model_readonly import _NoRedirects

    request = Request(single.BASE_URL + "/models", method="GET")
    with build_opener(ProxyHandler({}), _NoRedirects()).open(
        request, timeout=5
    ) as response:
        if response.geturl() != single.BASE_URL + "/models":
            return False
        models = single._read_json(response)
    return single._model_id(models) == EXPECTED_MODEL


def attempt():
    report = {
        "probe": "ventuno_existing_geniex_lazy_htp_activation_once",
        "status": "no_go",
        "opt_in_present": False,
        "single_geniex_idle_backend_verified": False,
        "declared_npu_compute_verified": False,
        "installed_qairt_246_runtime_pair_verified": False,
        "expected_exact_model_available": False,
        "memory_minimum_met": False,
        "same_service_mainpid_before_post": False,
        "http_post_attempted": False,
        "bounded_synthetic_reply_received": False,
        "existing_backend_associated_after_post": False,
        "same_service_mainpid_after_post": False,
        "sample": None,
        "npu_operator_placement_verified": False,
        "htp_cycles_or_utilization_measured": False,
        "new_htp_or_geniex_process_started": False,
        "service_or_model_configuration_modified": False,
        "model_response_text_exported": False,
        "personal_prompts_or_model_files_read": False,
        "permissions_or_firmware_modified": False,
    }
    if os.environ.get("MYAI_ALLOW_ONE_EXISTING_GENIEX_LAZY_HTP_REQUEST") != "yes":
        report["status"] = "no_go_explicit_opt_in_missing"
        return report
    report["opt_in_present"] = True

    pid, observed = _snapshot()
    if pid is None or not _idle_for_one_request(observed):
        report["status"] = "no_go_existing_worker_not_confidently_idle"
        return report
    report["single_geniex_idle_backend_verified"] = True

    startup = service_startup_hint()
    if not (
        startup.get("direct_geniex_serve_declared") is True
        and startup.get("declared_compute_hint") == "npu_requested_not_verified"
        and startup.get("qairt_override_option_declared") is False
    ):
        report["status"] = "no_go_declared_npu_service_config_unverified"
        return report
    report["declared_npu_compute_verified"] = True
    if not _package_pair_verified():
        report["status"] = "no_go_installed_qairt_runtime_pair_unverified"
        return report
    report["installed_qairt_246_runtime_pair_verified"] = True

    memory = single.available_memory_kib()
    if type(memory) is not int or memory < MIN_AVAILABLE_KIB:
        report["status"] = "no_go_insufficient_available_memory"
        return report
    report["memory_minimum_met"] = True

    # Network request is a fixed, direct localhost GET with no proxy
    # or redirects. Only this model ID can be used in the one POST.
    try:
        exact_model = _existing_model()
    except Exception:
        exact_model = False
    if not exact_model:
        report["status"] = "no_go_exact_model_catalog_unverified"
        return report
    report["expected_exact_model_available"] = True

    # Fail closed if the PID or descriptor state changed before POST.
    just_before_pid, just_before = _snapshot()
    if just_before_pid != pid or not _idle_for_one_request(just_before):
        report["status"] = "no_go_worker_changed_before_inference"
        return report
    report["same_service_mainpid_before_post"] = True

    try:
        report["http_post_attempted"] = True
        sample = single.run_one_synthetic_request(EXPECTED_MODEL)
        # Keep only the known safe sampling contract, never any reply.
        report["sample"] = sample
        report["bounded_synthetic_reply_received"] = (
            isinstance(sample, dict)
            and sample.get("response_nonempty") is True
            and sample.get("returned_text_logged") is False
        )
        report["status"] = "synthetic_response_backend_afterward_unverified"
    except Exception:
        report["status"] = "synthetic_request_failed_sanitized"
        # No exception contents, HTTP response or model output exported.
    finally:
        after_pid, after = _snapshot()
        report["same_service_mainpid_after_post"] = (
            after_pid == pid if after_pid is not None else False
        )
        mapped = after.get("mapped_libraries")
        mapped = mapped if isinstance(mapped, dict) else {}
        report["existing_backend_associated_after_post"] = bool(
            after_pid == pid
            and after.get("service_mainpid_present") is True
            and type(after.get("geniex_process_count")) is int
            and after["geniex_process_count"] == 1
            and after.get("complete_process_maps") is True
            and after.get("complete_fast_rpc_fd_scan") is True
            and after.get("runtime_backend_evidence") is True
            and mapped.get("libQnnHtp.so") is True
            and after.get("fast_rpc_secure_fd_open") is True
        )
    if report["bounded_synthetic_reply_received"]:
        report["status"] = (
            "existing_geniex_synthetic_reply_and_htp_association_only"
            if report["existing_backend_associated_after_post"] else
            "existing_geniex_synthetic_reply_without_htp_association"
        )
    return report


if __name__ == "__main__":
    try:
        output = attempt()
    except Exception:
        output = {
            "probe": "ventuno_existing_geniex_lazy_htp_activation_once",
            "status": "no_go_unexpected_exception",
            "npu_operator_placement_verified": False,
            "htp_cycles_or_utilization_measured": False,
            "new_htp_or_geniex_process_started": False,
            "service_or_model_configuration_modified": False,
            "model_response_text_exported": False,
        }
    print("MYAI_GENIEX_LAZY_HTP_ONCE_JSON=" + json.dumps(output, sort_keys=True))
