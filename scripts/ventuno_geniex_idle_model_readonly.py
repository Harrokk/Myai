"""Read-only GenieX model catalog and service startup-mode diagnostic.

The earlier device probe observed an active GenieX PID but no QNN HTP
library mapping and no secure FastRPC descriptor. Determine whether a
recognised model is listed while idle and whether the installed unit
*declares* direct GenieX serve / a compute hint. This diagnostic NEVER
starts inference, reloads a model or attempts HTP execution.

Only GET to the fixed localhost /v1/models endpoint is allowed (no proxy),
plus bounded systemctl show and existing reviewed /proc metadata. Never
export ExecStart, command arguments, model IDs, environment, service log,
paths, PIDs, HTTP response bodies, tokens or process memory.

Docs: https://github.com/qualcomm/GenieX/blob/main/docs/en/run/cli/reference.mdx
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from scripts.ventuno_existing_geniex_npu_backend_reasons_readonly import classify
from scripts.ventuno_geniex_runtime_attestation import (
    SERVICE, main_pid_from_systemd, summarize_service,
)
from scripts.ventuno_live_qairt_synthetic_once import (
    BASE_URL, _model_id, _read_json, available_memory_kib,
)

MAX_UNIT_BYTES = 8192
UNIT_ARG = ("systemctl", "show", SERVICE, "--property=ExecStart", "--value",
            "--no-pager")
DIRECT_SERVE = re.compile(
    r"^(?:/[-A-Za-z0-9_./]+/)?geniex\s+serve(?:\s|$)"
)
COMPUTE = re.compile(r"(?:^|\s)--compute(?:=|\s+)([^\s;]{1,40})(?=\s|$)")


def startup_hint(raw):
    """A limited lexical hint, never trusted as executed backend selection."""
    result = {
        "unit_command_inspection": "unavailable_or_indirect",
        "direct_geniex_serve_declared": False,
        "declared_compute_hint": "unknown",
        "qairt_override_option_declared": False,
        "unit_arguments_exported": False,
        "unit_environment_inspected": False,
    }
    if type(raw) is not str or not 1 <= len(raw) <= MAX_UNIT_BYTES:
        return result
    # systemctl show renders ExecStart={ path=... ; argv[]=... ; ... }.
    # Only parse one bounded argv[] field. Do not expose contents.
    entries = raw.split("argv[]=")
    if len(entries) != 2:
        return result
    argv = entries[1].split(";", 1)[0].strip()
    if not DIRECT_SERVE.match(argv):
        return result
    result["unit_command_inspection"] = "direct_geniex_serve_declared"
    result["direct_geniex_serve_declared"] = True
    result["qairt_override_option_declared"] = bool(
        re.search(r"(?:^|\s)--qairt-lib(?:=|\s)", argv)
    )
    choices = COMPUTE.findall(argv)
    if not choices:
        result["declared_compute_hint"] = "not_explicitly_selected"
    elif len(choices) == 1 and choices[0] == "npu":
        result["declared_compute_hint"] = "npu_requested_not_verified"
    elif len(choices) == 1 and choices[0] == "cpu":
        result["declared_compute_hint"] = "cpu_requested_not_verified"
    else:
        result["declared_compute_hint"] = "other_or_ambiguous"
    return result


def service_startup_hint():
    try:
        proc = subprocess.run(
            UNIT_ARG,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        if proc.returncode != 0 or len(proc.stdout) > MAX_UNIT_BYTES:
            return startup_hint(None)
        return startup_hint(proc.stdout.decode("utf-8", errors="replace"))
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        return startup_hint(None)


class _NoRedirects(HTTPRedirectHandler):
    """Never follow a model API redirect off the local device."""
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def fixed_loopback_catalog():
    """No proxy, redirects or requests to user-controlled endpoints."""
    result = "unavailable_or_unverified"
    request = Request(BASE_URL + "/models", method="GET")
    try:
        # No inherited proxy environment; no calls outside localhost.
        opener = build_opener(ProxyHandler({}), _NoRedirects())
        with opener.open(request, timeout=5) as response:
            # The response must come from the fixed local loopback endpoint.
            if response.geturl() != BASE_URL + "/models":
                return result
            catalog = _read_json(response)  # 128 KiB max, no emitted body
        result = (
            "expected_single_qairt_model_listed_not_execution_proof"
            if _model_id(catalog) is not None
            else "no_expected_single_qairt_model_in_catalog"
        )
    except Exception:
        pass  # Never export exception contents or URL details.
    return result


def snapshot():
    pid = main_pid_from_systemd()
    if type(pid) is not int or pid <= 1:
        return None, {}
    return pid, summarize_service(Path("/proc"), pid)


def report():
    startup = service_startup_hint()
    before_pid, before_raw = snapshot()
    ram = available_memory_kib()
    before = classify(before_raw, ram)
    model_state = fixed_loopback_catalog()
    after_pid, after_raw = snapshot()
    after = classify(after_raw, ram)

    same_pid = (
        before_pid is not None and after_pid is not None
        and before_pid == after_pid
    )
    if not same_pid:
        interpretation = "no_go_service_identity_unverified_or_changed"
    elif model_state != "expected_single_qairt_model_listed_not_execution_proof":
        interpretation = "no_go_pinned_model_catalog_unverified"
    elif before["backend_association_confirmed"] and after["backend_association_confirmed"]:
        interpretation = "existing_backend_association_only_not_htp_proof"
    elif after["backend_association_confirmed"]:
        interpretation = "backend_association_newly_observed_no_htp_proof"
    else:
        interpretation = "catalog_present_backend_not_observed_possible_idle_state"

    return {
        "probe": "ventuno_geniex_catalog_and_startup_readonly",
        "status": interpretation,
        "startup": startup,
        "model_catalog": model_state,
        "same_geniex_mainpid_across_get": same_pid,
        "backend_before_get": before,
        "backend_after_get": after,
        "http_methods_used": ["GET"],
        "http_post_performed": False,
        "model_inference_executed": False,
        "htp_graph_placement_verified": False,
        "npu_utilization_measured": False,
        "second_qnn_htp_client_started": False,
        "model_service_or_permissions_modified": False,
        "command_lines_or_service_environment_exported": False,
        "api_model_id_or_response_body_exported": False,
        "private_model_data_or_user_prompts_accessed": False,
    }


if __name__ == "__main__":
    try:
        record = report()
    except Exception:
        record = {
            "probe": "ventuno_geniex_catalog_and_startup_readonly",
            "status": "no_go_metadata_exception",
            "http_post_performed": False,
            "model_inference_executed": False,
            "htp_graph_placement_verified": False,
            "second_qnn_htp_client_started": False,
            "model_service_or_permissions_modified": False,
            "command_lines_or_service_environment_exported": False,
            "api_model_id_or_response_body_exported": False,
        }
    print("MYAI_GENIEX_IDLE_CATALOG_JSON=" + json.dumps(record, sort_keys=True))
