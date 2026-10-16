"""Aggregate *remote source-only* VENTUNO revision evidence with hard NO-GO.

This intentionally cannot grant final hardware/production sign-off.
It executes only repository source analyzers, never MyAI runtime, audio,
native models, subprocess workflows, package installers or services.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts import ventuno_deep_source_audit as deep
from scripts import ventuno_all_manual_actions_drift_gate as all_manual
from scripts import ventuno_manual_workflow_source_identity as identity
from scripts import ventuno_board_timer_quarantine as timers
from scripts import ventuno_main_workflow_quarantine as old_main
from scripts import ventuno_workflow_release_review as workflows

ROOT = Path(__file__).resolve().parent.parent


def closeout(root=ROOT):
    root = Path(root)
    try:
        source = deep.audit(root)
        manual = all_manual.inspect(root)
        oids = identity.check(root)
        timer = timers.check(root)
        quarantined_main = old_main.classify(root)
        branch = workflows.inventory(root, branch="main")
        path = root / "config/profiles/ventuno_q.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError("linked-or-missing-profile")
        profile = json.loads(path.read_text(encoding="utf-8"))
        settings_safe = (
            profile.get("voice", {}).get("enabled") is False
            and profile.get("voice", {}).get("tts_enabled") is False
            and profile.get("ventuno", {}).get("rpc_write_enabled") is False
        )
    except (OSError, UnicodeError, ValueError, TypeError, KeyError, AttributeError):
        source, manual, oids, timer, quarantined_main, branch = {}, {}, {}, {}, {}, {}
        settings_safe = False
    checks = {
        "two_pass_source_audit": deep.audit_exit_code(source) == 0,
        "all_103_manual_workflows_inventoried": manual.get("manual_workflow_source_inventory_complete") is True,
        "all_103_manual_workflow_contents_unchanged": oids.get("status") == "all-103-source-blobs-unchanged-not-authorized",
        "two_board_timer_jobs_inert": timer.get("status") == "two-board-timer-jobs-inert",
        "four_main_legacy_workflows_inert": quarantined_main.get("quarantine_verified") is True,
        "target_main_automatic_sensitive_workflows_absent": (
            branch.get("status") == "inventory-complete-not-release-authorized"
            and branch.get("candidate_automatic_clear") is True
            and branch.get("counts", {}).get("unparsed_event_workflow_files") == 0
        ),
        "default_voice_tts_and_rpc_write_off": settings_safe,
    }
    passed = all(checks.values())
    return {
        "status": "source-revision-checks-complete-with-physical-holds" if passed
                  else "blocked-source-revision-incomplete",
        "checks": checks,
        "remote_source_gates_passed": passed,
        "source_only_revision": True,
        "release_candidate_runtime_provenance_attested": False,
        "installed_voice_dependencies_verified": False,
        "effective_live_config_and_memory_separation_verified": False,
        "physical_microphone_stt_tts_stop_verified": False,
        "observed_latency_ram_temperature_verified": False,
        "native_htp_npu_profile_verified": False,
        "out_of_band_recovery_physically_verified": False,
        "full_indirect_action_script_security_review_signed_off": False,
        "operator_present_and_authorized": False,
        "source_checks_are_not_manual_line_by_line_certification": True,
        "all_hardware_revision_gates_closed": False,
        "main_merge_authorized": False,
        "production_deployment_authorized": False,
    }


def main():
    result = closeout()
    print("MYAI_FINAL_REMOTE_SOURCE_REVISION_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["remote_source_gates_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
