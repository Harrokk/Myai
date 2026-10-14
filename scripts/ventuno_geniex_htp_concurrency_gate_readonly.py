"""Read-only sanitised GenieX/HTP concurrency no-go on real VENTUNO.

Only systemctl show(MainPID) and bounded /proc file metadata are read.
Does NOT execute qnn-net-run, access DSP device nodes, modify services,
or expose PID, paths, descriptor targets or process command lines.
"""
import json
from pathlib import Path

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_tiny_qnn_htp_once import assess_geniex_concurrency


def report():
    assessment = summarize_service(Path("/proc"), main_pid_from_systemd())
    return {
        "probe": "ventuno_geniex_htp_concurrency_gate_readonly",
        "status": assess_geniex_concurrency(assessment),
        "geniex_service_mainpid_present":
            assessment.get("service_mainpid_present") is True,
        "geniex_process_found":
            type(assessment.get("geniex_process_count")) is int
            and assessment["geniex_process_count"] > 0,
        "fast_rpc_fd_scan_complete":
            assessment.get("complete_fast_rpc_fd_scan") is True,
        "process_maps_complete":
            assessment.get("complete_process_maps") is True,
        "secure_fastrpc_fd_observed":
            assessment.get("fast_rpc_secure_fd_open") is True,
        "htp_inference_attempted": False,
        "fast_rpc_device_open_attempted": False,
        "service_changed": False,
        "raw_pid_paths_fds_or_errors_exported": False,
    }


if __name__ == "__main__":
    print("MYAI_GENIEX_HTP_GATE_JSON=" + json.dumps(report(), sort_keys=True))
