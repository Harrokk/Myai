"""One-authorization READ-ONLY VENTUNO metadata bridge; never captures audio.

Invoked only by the uniquely branch-scoped self-hosted one-shot workflow,
after a separate hosted exact-SHA safety job. All child output and errors
remain private; exported evidence is allowlisted status/booleans/numbers.
No package install, NPU inference, mic, playback, services or production write.
"""
import argparse
import json
import os
from pathlib import Path
import platform
import pwd
import re
import subprocess
import sys

from scripts.ventuno_physical_pilot_gate import _get_exact_head

SHA = re.compile(r"[0-9a-f]{40}\Z")
MAX_STDOUT = 32768
PYTHON = Path("/home/arduino/MyAI/.venv/bin/python")


def _call_module(root, module, args, marker, *, time_limit=110,
                 python=PYTHON, executor=subprocess.run):
    """Bounded subprocess; never echo model/audio/PII/error text."""
    try:
        result = executor(
            [str(python), "-B", "-m", module, *args],
            cwd=str(root), text=True, capture_output=True, timeout=time_limit,
            check=False,
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C.UTF-8",
                "PYTHONDONTWRITEBYTECODE": "1",
            },
        )
        if (len(result.stdout) > MAX_STDOUT
                or len(result.stderr) > MAX_STDOUT
                or result.returncode not in (0, 2)):
            return {"status": "probe-error"}
        rows = [row for row in result.stdout.splitlines() if row.strip()]
        if marker:
            rows = [r.split(marker, 1)[1] for r in rows if r.startswith(marker)]
        if len(rows) != 1:
            return {"status": "probe-invalid-report"}
        report = json.loads(rows[0])
        if type(report) is not dict or type(report.get("status")) is not str:
            return {"status": "probe-invalid-report"}
        if result.returncode != 0 and report["status"] not in {
            "blocked-unpinned-source",
            "blocked-unsafe-production-profile",
            "blocked-active-production-profile",
            "blocked-read-only-board-preflight",
        }:
            return {"status": "probe-error"}
        return report
    except (OSError, ValueError, TypeError, subprocess.TimeoutExpired):
        return {"status": "probe-error"}


def summarize(pilot, idle, matrix):
    """Assess conservative board metadata only. Never approve physical audio."""
    pilot = pilot if type(pilot) is dict else {}
    idle = idle if type(idle) is dict else {}
    matrix = matrix if type(matrix) is dict else {}
    pilot_ok = all((
        pilot.get("status") == "board-readonly-preflight-passed",
        pilot.get("source_exact_sha") is True,
        pilot.get("source_config_default_off") is True,
        pilot.get("active_production_profile_default_off") is True,
        pilot.get("board_preflight_passed") is True,
        pilot.get("ready_for_separate_human_consent") is True,
        pilot.get("recording_authorized") is False,
        pilot.get("playback_authorized") is False,
        pilot.get("physical_recording_attempted") is False,
        pilot.get("model_loaded") is False,
        pilot.get("npu_tested") is False,
        pilot.get("production_changed") is False,
    ))
    idle_ok = all((
        idle.get("status") == "read-only-idle-baseline",
        idle.get("myai_service_active") is True,
        idle.get("geniex_service_active") is True,
        idle.get("runner_service_active") is True,
        idle.get("microphone_opened") is False,
        idle.get("services_modified") is False,
        idle.get("usb_audio_present") is True,
    ))
    matrix_ok = all((
        matrix.get("status") == "metadata-completed-needs-operator-test",
        matrix.get("board_usb_voice_metadata_ready") is True,
        matrix.get("read_only_npu_metadata_valid") is True,
        matrix.get("read_only_htp_capture_metadata_valid") is True,
        matrix.get("read_only_htp_concurrency_metadata_valid") is True,
        matrix.get("read_only_recovery_dryrun_metadata_valid") is True,
        matrix.get("all_five_probe_reports_present") is True,
        matrix.get("safe_to_request_separate_voice_consent") is True,
        matrix.get("physical_audio_authorized") is False,
        matrix.get("exclusive_npu_maintenance_authorized") is False,
        matrix.get("real_microphone_audio_tested_now") is False,
        matrix.get("real_speaker_playback_tested_now") is False,
        matrix.get("system_services_changed") is False,
    ))
    eligible = pilot_ok and idle_ok and matrix_ok
    def numeric(value, low, high):
        return value if type(value) in (int, float) and low <= value <= high else None
    return {
        "status": (
            "board-readonly-metadata-accepted"
            if eligible else "blocked-readonly-hardware-preflight"
        ),
        "runner_readonly_reached_board": True,
        "pilot_gate_status": (
            pilot.get("status") if type(pilot.get("status")) is str
            and len(pilot["status"]) < 70 else "invalid"
        ),
        "usb_voice_hardware_metadata_ready": pilot_ok,
        "idle_runtime_metadata_valid": idle_ok,
        "npu_htp_no_inference_metadata_valid": matrix_ok,
        "ram_available_gib": numeric(idle.get("ram_available_gib"), 0, 1000),
        "disk_available_gib": numeric(idle.get("disk_available_gib"), 0, 100000),
        "temperature_max_c": numeric(idle.get("temperature_max_c"), -20, 140),
        "myai_service_active": idle.get("myai_service_active") is True,
        "geniex_service_active": idle.get("geniex_service_active") is True,
        "usb_audio_present": idle.get("usb_audio_present") is True,
        "ready_for_separate_operator_consent_only": eligible,
        # Read-only source-and-metadata inspection must NEVER grant consent:
        "physical_recording_authorized": False,
        "physical_playback_authorized": False,
        "live_model_inference_performed": False,
        "npu_inference_performed": False,
        "critical_tool_execution_authorized": False,
        "production_modified": False,
        "separate_operator_consent_required": True,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--expected-sha", required=True)
    options = parser.parse_args(argv)
    try:
        root = options.source_root.resolve(strict=True)
        same_head = (
            type(options.expected_sha) is str
            and SHA.fullmatch(options.expected_sha) is not None
            and _get_exact_head(root) == options.expected_sha
        )
        permitted_context = all((
            os.environ.get("RUNNER_ENVIRONMENT") == "self-hosted",
            os.environ.get("GITHUB_REPOSITORY") == "Harrokk/Myai",
            os.environ.get("GITHUB_REF") ==
                "refs/heads/dev/ventuno-physical-readonly-once-20261104",
            platform.machine().lower() == "aarch64",
            os.geteuid() != 0,
            pwd.getpwuid(os.geteuid()).pw_name == "arduino",
            PYTHON.is_file(),
            os.environ.get("GITHUB_SHA") == options.expected_sha,
            same_head,
        ))
        if not permitted_context:
            raise ValueError("Unsafe board runner or source identity")
        pilot = _call_module(
            root, "scripts.ventuno_physical_pilot_gate",
            ["--source-root", str(root), "--expected-sha", options.expected_sha,
             "--board-readonly"], "", time_limit=100,
        )
        idle = _call_module(
            root, "scripts.ventuno_remote_idle_baseline",
            [], "MYAI_VENTUNO_IDLE_BASELINE_JSON=", time_limit=75,
        )
        matrix = _call_module(
            root, "scripts.ventuno_big_test_readiness",
            ["--board-metadata-only"], "MYAI_BIG_TEST_READINESS_JSON=",
            time_limit=120,
        )
        report = summarize(pilot, idle, matrix)
    except Exception:
        report = {
            "status": "blocked-readonly-hardware-preflight",
            "runner_readonly_reached_board": False,
            "physical_recording_authorized": False,
            "physical_playback_authorized": False,
            "npu_inference_performed": False,
            "critical_tool_execution_authorized": False,
            "production_modified": False,
            "separate_operator_consent_required": True,
        }
    print("MYAI_VENTUNO_ONE_SHOT_READONLY_JSON=" + json.dumps(
        report, sort_keys=True, separators=(",", ":"),
    ))
    return 0 if report["status"] == "board-readonly-metadata-accepted" else 2


if __name__ == "__main__":
    sys.exit(main())
