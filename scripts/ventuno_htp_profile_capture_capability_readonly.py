"""Non-invasive VENTUNO GenieX/QNN HTP profile capability decision.

The current upstream Qualcomm GenieX QAIRT plugin declares:
  core/include/types.h: enable_optrace, "Requires QAIRT 2.48+ at runtime."
  core/src/model_init.cpp: initializeHtp(..., enable_optrace, ...).
This upstream source does NOT prove the board's installed GenieX binary
supports or exposes that option, so do not infer it from documentation.

Only the installed QAIRT dpkg metadata and bounded --help responses from
geniex serve, qnn-net-run and qnn-profile-viewer are inspected. Never
enable profiling, load contexts, invoke net-run with inputs, attach ptrace,
read cached model/profile bytes, open DSP devices, or change services.
An available qnn-profile-viewer is a READER, not a capture API.
"""
from __future__ import annotations

import json
import platform

from scripts.ventuno_qairt_v75_package_readonly import package_versions
from scripts.ventuno_v75_npu_readiness_readonly import _installed_minor
from scripts.ventuno_qnn_profile_feasibility import command_help


UPSTREAM_OPTRACE_MIN = (2, 48)
# Strict observed flag names only. --log and API "timings" are NOT optrace.
GENIEX_OPTRACE_FLAGS = frozenset({
    "--enable-optrace", "--optrace", "--optrace-output-path",
    "--optrace-output", "--qnn-optrace",
})
QNN_CAPTURE_FLAG = "--profiling_level"
QNN_VIEWER_INPUT_FLAG = "--input_log"


def parse_minor(value):
    if type(value) is not str or len(value) > 16:
        return None
    parts = value.split(".")
    if len(parts) != 2 or any(not part.isascii() or not part.isdecimal() for part in parts):
        return None
    major, minor = (int(x) for x in parts)
    return (major, minor) if 0 <= major <= 99 and 0 <= minor <= 999 else None


def _flags(metadata):
    if not isinstance(metadata, dict):
        return set()
    entries = metadata.get("profile_relevant_flags", [])
    if not isinstance(entries, list) or len(entries) > 60:
        return set()
    return {
        item for item in entries
        if type(item) is str and item.startswith("--") and len(item) <= 48
    }


def classify(packages, geniex_help, netrun_help, viewer_help, machine):
    packages = packages if isinstance(packages, dict) else {}
    gflags, nflags, vflags = map(
        _flags, (geniex_help, netrun_help, viewer_help)
    )
    runtime = _installed_minor(packages.get("qairt-libs"))
    dsp = _installed_minor(packages.get("qairt-dsp-binaries"))
    parsed = parse_minor(runtime)
    both = runtime is not None and runtime == dsp
    # A newer SDK-version requirement is a prerequisite for the *upstream*
    # optrace plugin; no evidence it is present in the shipped GenieX build.
    upstream_min_met = bool(
        both and parsed is not None and parsed[0] == 2
        and parsed >= UPSTREAM_OPTRACE_MIN
    )
    reader_present = isinstance(viewer_help, dict) and viewer_help.get("available") is True
    netrun_present = isinstance(netrun_help, dict) and netrun_help.get("available") is True
    observed_geniex_cli_optrace = bool(gflags & GENIEX_OPTRACE_FLAGS)
    netrun_capture_flag = netrun_present and QNN_CAPTURE_FLAG in nflags
    viewer_input_flag = reader_present and QNN_VIEWER_INPUT_FLAG in vflags

    reasons = []
    if machine != "aarch64":
        reasons.append("not_on_ventuno_arm64")
    if not both:
        reasons.append("qairstack_runtime_pair_not_attested")
    if not upstream_min_met:
        reasons.append("upstream_geniex_optrace_min_248_not_met_or_unknown")
    if not observed_geniex_cli_optrace:
        reasons.append("installed_geniex_cli_optrace_flag_not_observed")
    if not netrun_capture_flag:
        reasons.append("qnn_netrun_capture_flag_not_observed")
    if not viewer_input_flag:
        reasons.append("qnn_viewer_input_flag_not_observed")
    # Always NO-GO: --help cannot prove a server has a live in-process
    # QNN profile capture API, nor that an independent HTP model/context
    # can be loaded safely alongside the existing 4B GenieX session.
    reasons.append("live_geniex_inprocess_profile_capture_not_verified")
    reasons.append("independent_htp_capture_model_and_exclusive_window_not_verified")

    return {
        "probe": "ventuno_htp_profiling_capture_capability_readonly",
        "status": "no_go_direct_htp_profile_not_yet_reproducible",
        "observations": reasons,
        "target_is_aarch64": machine == "aarch64",
        "runtime_and_dsp_minor_match": both,
        "installed_runtime_minor_is_246": both and runtime == "2.46",
        "upstream_plugin_optrace_min_runtime": "2.48",
        "upstream_plugin_optrace_runtime_requirement_met": upstream_min_met,
        "installed_geniex_cli_optrace_option_observed": observed_geniex_cli_optrace,
        "installed_geniex_plugin_optrace_supported_verified": False,
        "qnn_net_run_profiling_flag_observed": netrun_capture_flag,
        "qnn_profile_viewer_input_flag_observed": viewer_input_flag,
        "qnn_profile_viewer_reads_existing_logs_only": True,
        "qnn_net_run_is_separate_inference_process": True,
        "independent_safe_htp_model_and_input_ready": False,
        "live_inprocess_qnn_profile_session_verified": False,
        "htp_per_op_cycles_measured": False,
        "model_graph_placement_verified": False,
        "live_service_restart_or_stop_performed": False,
        "profile_log_or_private_model_read": False,
        "new_model_or_qnn_client_started": False,
        "device_or_firmware_modified": False,
        "raw_cli_output_or_paths_exported": False,
    }


def report():
    return classify(
        package_versions(),
        command_help("geniex", "serve"),
        command_help("qnn-net-run"),
        command_help("qnn-profile-viewer"),
        platform.machine().lower(),
    )


if __name__ == "__main__":
    try:
        result = report()
    except Exception:
        result = {
            "probe": "ventuno_htp_profiling_capture_capability_readonly",
            "status": "no_go_metadata_probe_failed",
            "htp_per_op_cycles_measured": False,
            "model_graph_placement_verified": False,
            "live_service_restart_or_stop_performed": False,
            "new_model_or_qnn_client_started": False,
            "device_or_firmware_modified": False,
            "raw_cli_output_or_paths_exported": False,
        }
    print("MYAI_HTP_PROFILE_CAPABILITY_JSON=" + json.dumps(result, sort_keys=True))
