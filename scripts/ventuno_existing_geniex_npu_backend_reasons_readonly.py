"""Read-only reason codes for an inconclusive existing GenieX/HTP gate.

Inspect only the current systemd service MainPID and bounded /proc evidence
via existing reviewed attestation helpers. Never call /chat/completions,
invoke QNN, open a DSP device or change runtime, models or permissions.

A missing mapped library or FastRPC descriptor is an OBSERVATION, not
a proof that the NPU is unavailable, unused or misconfigured.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_live_qairt_synthetic_once import (
    MEMORY_MIN_KIB, available_memory_kib,
)


def classify(snapshot, free_kib):
    """Emit only fixed allowlisted flags/reasons; no process or path data."""
    state = snapshot if isinstance(snapshot, dict) else {}
    libraries = state.get("mapped_libraries")
    libraries = libraries if isinstance(libraries, dict) else {}
    pid_present = state.get("service_mainpid_present") is True
    count = state.get("geniex_process_count")
    exact_one = type(count) is int and count == 1
    maps_complete = state.get("complete_process_maps") is True
    fds_complete = state.get("complete_fast_rpc_fd_scan") is True
    htp_mapped = libraries.get("libQnnHtp.so") is True
    stub_mapped = libraries.get("libQnnHtpV75Stub.so") is True
    fastrpc_open = state.get("fast_rpc_secure_fd_open") is True
    mem_ok = type(free_kib) is int and free_kib >= MEMORY_MIN_KIB
    observations = []
    if not pid_present:
        observations.append("geniex_service_mainpid_not_verified")
    if not exact_one:
        observations.append("exactly_one_geniex_process_not_verified")
    if not maps_complete:
        observations.append("complete_geniex_maps_not_verified")
    if not fds_complete:
        observations.append("complete_geniex_fd_scan_not_verified")
    if not htp_mapped:
        observations.append("geniex_htp_library_mapping_not_observed")
    if not fastrpc_open:
        observations.append("geniex_secure_fastrpc_descriptor_not_observed")
    if not mem_ok:
        observations.append("available_memory_threshold_not_met_or_unknown")

    # HTP V75 Stub mapping is useful additional metadata but not
    # always proof of model/graph placement; it is not required here.
    confirmed = (
        pid_present and exact_one and maps_complete and fds_complete
        and htp_mapped and fastrpc_open and mem_ok
        and state.get("runtime_backend_evidence") is True
        and state.get("status") == "backend-associated-with-service"
    )
    if not confirmed and not observations:
        observations.append("attestation_contract_not_fully_satisfied")

    return {
        "probe": "ventuno_existing_geniex_npu_backend_reasons_readonly",
        "status": (
            "existing_backend_association_observed_not_htp_execution_proof"
            if confirmed else "no_go_existing_backend_association_inconclusive"
        ),
        "observations": observations,
        "service_mainpid_present": pid_present,
        "exactly_one_geniex_process_seen": exact_one,
        "geniex_process_maps_fully_readable": maps_complete,
        "geniex_fds_fully_readable": fds_complete,
        "geniex_htp_host_library_mapped": htp_mapped,
        "geniex_htp_v75_stub_mapped": stub_mapped,
        "geniex_secure_fastrpc_fd_observed": fastrpc_open,
        "ram_threshold_met": mem_ok,
        "backend_association_confirmed": confirmed,
        "graph_operator_placement_measured": False,
        "actual_htp_npu_execution_proven": False,
        "synthetic_prompt_posted": False,
        "qnn_backend_executed": False,
        "device_opened": False,
        "model_or_service_modified": False,
        "personal_content_or_raw_process_data_logged": False,
    }


def report():
    pid = main_pid_from_systemd()
    evidence = (
        summarize_service(Path("/proc"), pid)
        if type(pid) is int and pid > 1 else {}
    )
    return classify(evidence, available_memory_kib())


if __name__ == "__main__":
    try:
        observed = report()
    except Exception:
        observed = {
            "probe": "ventuno_existing_geniex_npu_backend_reasons_readonly",
            "status": "no_go_metadata_exception",
            "observations": ["metadata_inspection_unavailable"],
            "synthetic_prompt_posted": False,
            "qnn_backend_executed": False,
            "actual_htp_npu_execution_proven": False,
            "device_opened": False,
            "model_or_service_modified": False,
            "personal_content_or_raw_process_data_logged": False,
        }
    print("MYAI_EXISTING_GENIEX_BACKEND_REASONS_JSON=" + json.dumps(
        observed, sort_keys=True
    ))
