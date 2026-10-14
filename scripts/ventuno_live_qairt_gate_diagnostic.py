"""Read-only redacted follow-up to a failed GenieX HTP/FastRPC preflight.

Never invoke model inference, open microphones, mutate services, print PIDs,
process paths, command lines, network addresses, or HTTP response bodies.
"""

import json
import subprocess
from pathlib import Path
from urllib.request import urlopen

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_live_qairt_synthetic_once import (
    BASE_URL, _model_id, _read_json, available_memory_kib, backend_gate,
)


def _service_active(name):
    try:
        p = subprocess.run(
            ["systemctl", "is-active", "--", name],
            capture_output=True, text=True, timeout=4, check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "unknown"
    result = p.stdout.strip().lower()
    return result if result in ("active", "inactive", "failed", "activating") else "unknown"


def read_only_diagnostics():
    evidence = summarize_service(Path("/proc"), main_pid_from_systemd())
    available = available_memory_kib()
    model_endpoint = "unverified"
    try:
        with urlopen(BASE_URL + "/models", timeout=5) as response:
            model_endpoint = (
                "expected_qualcomm_qwen_model_present"
                if _model_id(_read_json(response)) is not None
                else "no_expected_model"
            )
    except Exception:
        model_endpoint = "unavailable"
    return {
        "mode": "no_inference_diagnostic",
        "systemd_geniex": _service_active("myai-geniex.service"),
        "systemd_myai": _service_active("myai-ventuno.service"),
        "backend_status": str(evidence.get("status", "missing"))[:90],
        "service_mainpid_present": evidence.get("service_mainpid_present") is True,
        "geniex_process_count": evidence.get("geniex_process_count"),
        "complete_process_maps": evidence.get("complete_process_maps") is True,
        "htp_library_mapped": bool(
            (evidence.get("mapped_libraries") or {}).get("libQnnHtp.so")),
        "fastrpc_secure_fd_open": evidence.get("fast_rpc_secure_fd_open") is True,
        "memory_available_at_least_3_gib": (
            available is not None and available >= 3 * 1048576),
        "backend_gate": backend_gate(evidence, available),
        "loopback_model_endpoint": model_endpoint,
        "http_post_performed": False,
        "model_started": False,
        "services_modified": False,
    }


if __name__ == "__main__":
    print("MYAI_LIVE_QAIRT_GATE_DIAGNOSTIC_JSON=" +
          json.dumps(read_only_diagnostics(), sort_keys=True))
