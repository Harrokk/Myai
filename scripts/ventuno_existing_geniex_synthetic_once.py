"""One explicitly opted-in synthetic request to an ALREADY RUNNING GenieX.

This NEVER starts a secondary QNN/HTP client, reloads a model, stops
GenieX, changes systemd or device rights, or reads private prompts.
It refuses to POST unless a complete process+FastRPC metadata scan
attests exactly one stable existing GenieX backend with spare memory.

One synthetic API response is application-level evidence, NOT per-op HTP
profiling or proof of NPU graph/operator placement. Only allowlisted
booleans and bounded timing counters are printed.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from scripts import ventuno_live_qairt_synthetic_once as single
from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)


def _stable_backend(snapshot):
    """Require strong provenance, not a momentary negative FD scan."""
    if not isinstance(snapshot, dict):
        return False
    return (
        snapshot.get("service_mainpid_present") is True
        and type(snapshot.get("geniex_process_count")) is int
        and snapshot["geniex_process_count"] == 1
        and snapshot.get("complete_fast_rpc_fd_scan") is True
        and snapshot.get("complete_process_maps") is True
        and snapshot.get("runtime_backend_evidence") is True
        and snapshot.get("fast_rpc_secure_fd_open") is True
        and isinstance(snapshot.get("mapped_libraries"), dict)
        and snapshot["mapped_libraries"].get("libQnnHtp.so") is True
        and snapshot.get("status") == "backend-associated-with-service"
    )


def _snapshot():
    pid = main_pid_from_systemd()
    if type(pid) is not int or pid <= 1:
        return None, {}
    return pid, summarize_service(Path("/proc"), pid)


def attempt():
    result = {
        "probe": "one_existing_geniex_synthetic_htp_association_check",
        "status": "no_go",
        "opt_in_verified": False,
        "complete_existing_backend_attested_before_post": False,
        "existing_backend_attested_after_post": False,
        "same_existing_service_mainpid_after_post": None,
        "http_post_performed": False,
        "synthetic_response_received": False,
        "sample": None,
        "npu_per_op_profile_measured": False,
        "htp_operator_placement_verified": False,
        "htp_accelerator_utilization_measured": False,
        "secondary_qnn_htp_client_started": False,
        "model_started_or_reloaded": False,
        "user_content_read_or_logged": False,
        "actual_response_text_logged": False,
        "existing_service_or_permissions_modified": False,
    }
    if os.environ.get("MYAI_ALLOW_EXISTING_GENIEX_SYNTHETIC_ONCE") != "yes":
        result["status"] = "no_go_not_authorized"
        return result
    result["opt_in_verified"] = True

    pid, observed = _snapshot()
    if pid is None or not _stable_backend(observed):
        result["status"] = "no_go_existing_geniex_backend_unverified"
        return result
    if single.backend_gate(observed, single.available_memory_kib()) != (
        "ready_for_single_synthetic_request"
    ):
        result["status"] = "no_go_existing_backend_or_ram_unverified"
        return result
    result["complete_existing_backend_attested_before_post"] = True

    try:
        # GET /models is bounded and local-only. No new model load.
        with single.urlopen(single.BASE_URL + "/models", timeout=5) as response:
            listed = single._read_json(response)
        model_id = single._model_id(listed)
        if model_id is None:
            result["status"] = "no_go_unexpected_existing_model"
            return result
        # Fail closed if systemd switched the process after the preview.
        if main_pid_from_systemd() != pid:
            result["status"] = "no_go_geniex_restarted_during_preflight"
            return result

        result["http_post_performed"] = True
        result["sample"] = single.run_one_synthetic_request(model_id)
        result["synthetic_response_received"] = True
        after_pid, after = _snapshot()
        result["same_existing_service_mainpid_after_post"] = (
            after_pid == pid if after_pid is not None else False
        )
        result["existing_backend_attested_after_post"] = (
            after_pid == pid and _stable_backend(after)
        )
        result["status"] = (
            "existing_geniex_responded_htp_placement_unverified"
            if result["existing_backend_attested_after_post"] else
            "existing_geniex_response_but_backend_afterward_unverified"
        )
    except Exception:
        # Do not reveal external HTTP exception bodies, URLs, process
        # metadata or vendor message details, even in a failure.
        result["status"] = "existing_geniex_request_or_attestation_failed"
        result["sample"] = None
        result["synthetic_response_received"] = False
    return result


if __name__ == "__main__":
    print("MYAI_EXISTING_GENIEX_SYNTHETIC_JSON=" + json.dumps(
        attempt(), sort_keys=True
    ))
