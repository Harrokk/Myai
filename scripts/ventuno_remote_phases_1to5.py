"""Read-only source gate for isolated ARM64 voice preflight phases 1-5.

No packages are installed, no device opened, no services modified. This
gate is deliberately NO-GO for physical execution until operator checks.
"""
from __future__ import annotations

import json
from pathlib import Path

from scripts.ventuno_main_workflow_quarantine import classify as quarantine
from scripts.ventuno_voice_static_lock_check import inspect as voice_lock
from scripts.ventuno_isolated_voice_stage_contract import candidate, SOURCE
from core.runtime_safety_attestation import summarize

ROOT = Path(__file__).resolve().parents[1]


def inspect(root=ROOT):
    q = quarantine(root)
    v = voice_lock(root)
    try:
        profile = root / "config/profiles/ventuno_q.json"
        settings = candidate(json.loads(profile.read_text(encoding="utf-8")))
        safe = summarize(settings, pid=1)["voice_and_writes_off"]
    except (OSError, ValueError, TypeError, KeyError):
        safe = False
    return {
        "status": ("source-only-phases-1-to-5-ready"
                   if q["quarantine_verified"] and v["source_lock_consistent"] and safe
                   else "blocked-source-preflight"),
        "legacy_workflows_quarantined": q["quarantine_verified"],
        "all_28_wheel_hashes_source_locked": v["source_lock_consistent"],
        "isolated_profile_risk_switches_off": safe,
        "isolated_native_venv_installed": False,
        "synthetic_stt_tts_e2e_executed": False,
        "live_effective_config_attested": False,
        "crash_recovery_physically_tested": False,
        "npu_htp_authorized": False,
        "audio_capture_authorized": False,
        "release_deployed": False,
    }


if __name__ == "__main__":
    print("MYAI_REMOTE_PHASES_1_TO_5_JSON=" + json.dumps(inspect(), sort_keys=True))
