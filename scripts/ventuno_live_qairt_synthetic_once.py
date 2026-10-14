"""One tiny synthetic prompt to an ALREADY RUNNING GenieX QAIRT service.

Explicitly opt-in through the GitHub workflow. Does not start models,
reload services, touch source files or use private prompts. Output contains
only bounded timing and boolean status: NEVER generated response text.
HTP process evidence is *not* a direct HTP utilization/profile measurement.
"""

import json
import math
import os
import re
import time
from urllib.request import Request, urlopen

from scripts.ventuno_geniex_runtime_attestation import (
    main_pid_from_systemd, summarize_service,
)
from pathlib import Path


BASE_URL = "http://127.0.0.1:18181/v1"
SYNTHETIC_PROMPT = "Compute 7 + 5. Reply only with the integer result."
MAX_GENERATED_TOKENS = 24
MEMORY_MIN_KIB = 3 * 1024 * 1024
_MAX_JSON_BYTES = 128 * 1024


def available_memory_kib():
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            match = re.fullmatch(r"MemAvailable:\s+(\d+)\s+kB", line.strip())
            if match:
                return int(match.group(1))
    except (OSError, UnicodeError):
        pass
    return None


def backend_gate(attestation, available_kib):
    """Refuse inference if process HTP/FastRPC provenance is not confirmed."""
    if not isinstance(attestation, dict):
        return "no_go_backend_unknown"
    libs = attestation.get("mapped_libraries")
    if (
        attestation.get("status") != "backend-associated-with-service"
        or attestation.get("runtime_backend_evidence") is not True
        or attestation.get("fast_rpc_secure_fd_open") is not True
        or not isinstance(libs, dict)
        or libs.get("libQnnHtp.so") is not True
    ):
        return "no_go_backend_unverified"
    if available_kib is None or available_kib < MEMORY_MIN_KIB:
        return "no_go_low_or_unknown_available_memory"
    return "ready_for_single_synthetic_request"


def _read_json(response):
    # Response limit protects the temporary Actions Python process.
    raw = response.read(_MAX_JSON_BYTES + 1)
    if len(raw) > _MAX_JSON_BYTES:
        raise ValueError("bounded_json_response_too_large")
    value = json.loads(raw)
    if not isinstance(value, dict):
        raise ValueError("invalid_json_response_shape")
    return value


def _model_id(models):
    options = models.get("data")
    if not isinstance(options, list) or len(options) != 1:
        return None
    entry = options[0]
    if not isinstance(entry, dict):
        return None
    label = entry.get("id")
    if (
        not isinstance(label, str) or len(label) > 160
        or not label.startswith("qualcomm/")
        or "Qwen" not in label
        or "W4A16" not in label
    ):
        return None
    return label


def _positive_metric(metrics, field):
    value = metrics.get(field)
    if type(value) in (int, float) and math.isfinite(value) and 0 <= value < 1e8:
        return round(float(value), 2)
    return None


def _safe_sample(response, duration):
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        raise ValueError("no_choices")
    choice = choices[0]
    if not isinstance(choice, dict):
        raise ValueError("invalid_choice")
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, str) or not content.strip():
        raise ValueError("empty_response")
    usage = response.get("usage")
    timing = response.get("timings")
    usage = usage if isinstance(usage, dict) else {}
    timing = timing if isinstance(timing, dict) else {}
    count = usage.get("completion_tokens")
    count = count if type(count) is int and 0 <= count <= MAX_GENERATED_TOKENS else None
    return {
        "response_nonempty": True,
        "returned_text_logged": False,
        "wall_seconds": round(duration, 3),
        "completion_tokens": count,
        "prompt_tokens": usage.get("prompt_tokens") if type(usage.get("prompt_tokens")) is int else None,
        "decode_tokens_per_second": _positive_metric(timing, "predicted_per_second"),
        "prompt_tokens_per_second": _positive_metric(timing, "prompt_per_second"),
    }


def run_one_synthetic_request(model_id, *, api_base=BASE_URL):
    payload = json.dumps({
        "model": model_id,
        "messages": [{"role": "user", "content": SYNTHETIC_PROMPT}],
        "temperature": 0,
        "max_tokens": MAX_GENERATED_TOKENS,
        "stream": False,
    }).encode("utf-8")
    request = Request(
        api_base + "/chat/completions",
        data=payload, headers={"Content-Type": "application/json"},
        method="POST",
    )
    start = time.monotonic()
    with urlopen(request, timeout=30) as response:
        data = _read_json(response)
    return _safe_sample(data, time.monotonic() - start)


def probe():
    evidence = summarize_service(Path("/proc"), main_pid_from_systemd())
    mem = available_memory_kib()
    gate = backend_gate(evidence, mem)
    report = {
        "probe": "live_existing_geniex_one_synthetic_prompt",
        "status": gate,
        "active_qnn_htp_and_fastrpc_attested": gate == "ready_for_single_synthetic_request",
        "live_services_modified": False,
        "model_restarted": False,
        "second_model_loaded": False,
        "synthetic_input_only": True,
        "user_text_or_audio_read": False,
        "generated_text_logged": False,
        "npu_per_op_profile_measured": False,
        "sample": None,
    }
    if gate != "ready_for_single_synthetic_request":
        return report
    if os.environ.get("MYAI_ALLOW_SYNTHETIC_GENIEX_REQUEST") != "yes":
        report["status"] = "no_go_no_explicit_synthetic_request_authorization"
        return report

    try:
        with urlopen(BASE_URL + "/models", timeout=5) as response:
            models = _read_json(response)
        model_id = _model_id(models)
        if model_id is None:
            report["status"] = "no_go_unrecognized_existing_model"
            return report
        report["sample"] = run_one_synthetic_request(model_id)
        report["status"] = "existing_qairt_service_generated_synthetic_response"
    except Exception as error:
        # Do not log URL, model paths, process IDs, user text or raw errors.
        report["status"] = "synthetic_request_error"
        report["error_category"] = type(error).__name__[:40]
    return report


if __name__ == "__main__":
    print("MYAI_LIVE_QAIRT_SYNTHETIC_RESULT_JSON=" + json.dumps(probe(), sort_keys=True))
