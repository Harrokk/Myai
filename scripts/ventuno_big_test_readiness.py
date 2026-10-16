"""Privacy-sanitized, non-invasive VENTUNO test-campaign evidence.

Only existing read-only metadata probes are called. No USB device is opened,
model loaded, NPU inference launched, profile capture enabled, unit restarted,
process killed or production file changed. Status is NEVER test authorization.
"""
from __future__ import annotations

import argparse
import json
from collections.abc import Callable
from typing import Any

PROBE_NAMES = ("voice", "npu", "htp_capture", "htp_concurrency", "recovery")

EXPECTED = {
    "voice": "ready-for-separate-consented-dialogue-test",
    "npu": "no_go",
    "htp_capture": "no_go_direct_htp_profile_not_yet_reproducible",
    "recovery": "no_go_dry_run_only",
}


def classify(observations: dict[str, object]) -> dict[str, object]:
    def row(name: str) -> dict[str, object]:
        obj = observations.get(name)
        if not isinstance(obj, dict):
            return {}
        return obj

    voice, npu, htp, concurrent, restore = (
        row(name) for name in PROBE_NAMES
    )
    sound_ok = all((
        voice.get("status") == EXPECTED["voice"],
        voice.get("arm64") is True,
        voice.get("production_voice_disabled") is True,
        voice.get("services_active") is True,
        voice.get("usb_capture_and_playback_1_0_accessible") is True,
        voice.get("ram_gate_passed") is True,
        voice.get("disk_gate_passed") is True,
        voice.get("microphone_opened") is False,
        voice.get("speaker_opened") is False,
        voice.get("model_loaded") is False,
        voice.get("physical_dialogue_attempted") is False,
        voice.get("production_changed") is False,
    ))
    npu_safe = all((
        npu.get("status") == EXPECTED["npu"],
        npu.get("qnn_or_htp_attempted") is False,
        npu.get("npu_inference_verified") is False,
        npu.get("npu_operator_placement_measured") is False,
        npu.get("devices_opened") is False,
        npu.get("service_or_packages_modified") is False,
    ))
    htp_safe = all((
        htp.get("status") == EXPECTED["htp_capture"],
        htp.get("htp_per_op_cycles_measured") is False,
        htp.get("model_graph_placement_verified") is False,
        htp.get("new_model_or_qnn_client_started") is False,
        htp.get("live_service_restart_or_stop_performed") is False,
        htp.get("device_or_firmware_modified") is False,
    ))
    concurrent_safe = all((
        type(concurrent.get("status")) is str,
        concurrent.get("htp_inference_attempted") is False,
        concurrent.get("fast_rpc_device_open_attempted") is False,
        concurrent.get("service_changed") is False,
    ))
    restore_safe = all((
        restore.get("status") == EXPECTED["recovery"],
        restore.get("qnn_htp_executed") is False,
        restore.get("npu_profile_measured") is False,
        restore.get("service_control_commands_executed") is False,
        restore.get("service_changes_authorized") is False,
        restore.get("out_of_band_recovery_verified") is False,
    ))
    all_observed = all(
        isinstance(observations.get(name), dict)
        for name in PROBE_NAMES
    )
    no_unintended_effects = all_observed and all(
        (npu_safe, htp_safe, concurrent_safe, restore_safe)
    )
    # Metadata-only NPU runs are fundamentally insufficient for profiling
    # permission regardless of any nominally green hardware prereqs.
    return {
        "status": (
            "metadata-completed-needs-operator-test"
            if no_unintended_effects else "incomplete-or-unsafe-metadata"
        ),
        "board_usb_voice_metadata_ready": sound_ok,
        "read_only_npu_metadata_valid": npu_safe,
        "read_only_htp_capture_metadata_valid": htp_safe,
        "read_only_htp_concurrency_metadata_valid": concurrent_safe,
        "read_only_recovery_dryrun_metadata_valid": restore_safe,
        "all_five_probe_reports_present": all_observed,
        "safe_to_request_separate_voice_consent": bool(sound_ok and no_unintended_effects),
        "exclusive_npu_maintenance_authorized": False,
        "physical_audio_authorized": False,
        "real_microphone_audio_tested_now": False,
        "real_speaker_playback_tested_now": False,
        "htp_operator_placement_verified": False,
        "npu_cycles_measured": False,
        "automatic_rollback_armed": False,
        "system_services_changed": False,
        "human_operator_verification_still_required": True,
    }


def collect(readers: dict[str, Callable[[], dict[str, object]]]
            ) -> dict[str, dict[str, object]]:
    """Treat *every* exception as absent evidence; never print raw errors."""
    results = {}
    for name in PROBE_NAMES:
        try:
            reader = readers.get(name)
            result = reader() if callable(reader) else None
            results[name] = result if isinstance(result, dict) else {}
        except Exception:
            results[name] = {}
    return results


def existing_readers() -> dict[str, Callable[[], dict[str, object]]]:
    # Existing modules are read-only inventories, not native inference.
    # Import lazily so synthetic tests cannot accidentally probe hardware.
    from scripts.ventuno_usb_voice_dialog_readiness import inspect as usb
    from scripts.ventuno_v75_npu_readiness_readonly import report as npu
    from scripts.ventuno_htp_profile_capture_capability_readonly import report as cap
    from scripts.ventuno_geniex_htp_concurrency_gate_readonly import report as concurrent
    from scripts.ventuno_htp_maintenance_recovery_dryrun import report as recovery
    return {
        "voice": usb, "npu": npu, "htp_capture": cap,
        "htp_concurrency": concurrent, "recovery": recovery,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--board-metadata-only", action="store_true",
        help="Opt in to existing read-only local inventory; no native inference",
    )
    args = parser.parse_args(argv)
    if not args.board_metadata_only:
        evidence: dict[str, dict[str, object]] = {}
    else:
        try:
            evidence = collect(existing_readers())
        except Exception:
            evidence = {}
    result = classify(evidence)
    print("MYAI_BIG_TEST_READINESS_JSON=" + json.dumps(result, sort_keys=True))
    # The command is a *diagnostic*. An incomplete inventory is not CI
    # execution failure, but it is always a user-facing NO-GO.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
