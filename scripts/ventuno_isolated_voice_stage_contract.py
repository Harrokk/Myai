"""Offline-only, fail-closed staging contract for a future VENTUNO voice pilot.

Never installs dependencies, creates a database, enables voice, imports audio
providers, loads a model, opens devices or changes installed production files.
No CLI option to authorize microphone capture, playback or NPU execution.
"""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

from core.config import DEFAULT_SETTINGS, _merge_settings
from core.config_validation import validate_settings
from scripts.ventuno_physical_pilot_gate import _config_safe


SOURCE = Path(__file__).resolve().parents[1] / "config/profiles/ventuno_q.json"
STAGE = Path(__file__).resolve().parents[1] / "config/profiles/ventuno_voice_trial_DISABLED.json"
STAGING_MEMORY = "runtime/isolated_voice_trial/memory.db"
STAGING_PREFIX = "runtime/isolated_voice_trial/"

# Deliberately config-contract only. A future operator can separately stage
# reviewed packages and an actual consented execution; THIS cannot do so.
VOICE_SAFE = {
    "enabled": False,
    "tts_enabled": False,
    "handsfree_enabled": False,
    "stt_model": "tiny",
    "stt_device": "cpu",
    "stt_compute_type": "int8",
    "stt_process_isolation_enabled": True,
    "stt_persistent_worker_enabled": False,
    "stt_process_timeout_seconds": 45.0,
    "stt_child_cpu_seconds": 30,
    "stt_child_virtual_memory_mib": 0,  # RLIMIT_AS 0: no fabricated cap.
    "backup_stt_models": [],
    "llm_streaming_enabled": False,
    "redundancy_enabled": False,
    "semantic_consensus_enabled": False,
}


def candidate(source):
    if not isinstance(source, dict) or not _config_safe(source):
        raise ValueError("Unreviewed unsafe source production profile")
    values = deepcopy(source)
    # Source may omit defaults; explicit stage choices live in the merged
    # effective config and are NEVER written back to the source document.
    # Match MyAI's real explicit-profile merge semantics exactly.
    # No runtime initialization or file creation is performed.
    settings = _merge_settings(DEFAULT_SETTINGS, values)
    voice = settings["voice"]
    voice.update(VOICE_SAFE)
    settings["memory"].update({
        "database": STAGING_MEMORY,
        "auto_assess_enabled": False,
        "auto_save_enabled": False,
        "review_queue_enabled": False,
        "lifecycle_enabled": False,
        "permanent_delete_enabled": False,
    })
    for key in ("camera", "location", "trusted_terminals", "hardware_watch", "vision"):
        settings[key]["enabled"] = False
    settings["selfdev"]["enabled"] = False
    settings["selfdev"]["promotion_enabled"] = False
    settings["files"]["enabled"] = False
    settings["files"]["write_enabled"] = False
    settings["files"]["workspace_root"] = STAGING_PREFIX + "workspace"
    settings["excel"]["enabled"] = False
    settings["excel"]["write_enabled"] = False
    settings["ventuno"]["rpc_enabled"] = False
    settings["ventuno"]["rpc_write_enabled"] = False
    settings["geniex_supervisor"]["restart_enabled"] = False
    settings["logging"]["jsonl_max_bytes"] = 100000
    settings["error_logging"]["path"] = STAGING_PREFIX + "errors.jsonl"
    settings["audit_logging"]["path"] = STAGING_PREFIX + "audit.jsonl"
    settings["runtime"]["heartbeat_path"] = STAGING_PREFIX + "heartbeat.json"
    settings["health"]["state_path"] = STAGING_PREFIX + "health.json"
    settings["geniex_supervisor"]["state_path"] = STAGING_PREFIX + "geniex.json"
    settings["stability_analysis"]["log_path"] = STAGING_PREFIX + "stability.jsonl"
    return settings


def attest(settings):
    if not isinstance(settings, dict):
        return False
    voice = settings.get("voice", {})
    memory = settings.get("memory", {})
    files = settings.get("files", {})
    checks = (
        all(voice.get(k) is v for k, v in VOICE_SAFE.items()
            if isinstance(v, bool)),
        voice.get("stt_model") == "tiny",
        voice.get("stt_device") == "cpu",
        voice.get("stt_compute_type") == "int8",
        memory.get("database") == STAGING_MEMORY,
        all(memory.get(k) is False for k in (
            "auto_assess_enabled", "auto_save_enabled", "review_queue_enabled",
            "lifecycle_enabled", "permanent_delete_enabled",
        )),
        files.get("enabled") is False,
        files.get("write_enabled") is False,
        settings.get("ventuno", {}).get("rpc_write_enabled") is False,
        settings.get("selfdev", {}).get("enabled") is False,
        settings.get("selfdev", {}).get("promotion_enabled") is False,
        settings.get("geniex_supervisor", {}).get("restart_enabled") is False,
        all(settings.get(k, {}).get("enabled") is False
            for k in ("camera", "location", "trusted_terminals", "hardware_watch", "vision")),
        settings.get("excel", {}).get("write_enabled") is False,
        all(settings.get(section, {}).get(field, "").startswith(STAGING_PREFIX)
            for section, field in (
                ("error_logging", "path"), ("audit_logging", "path"),
                ("runtime", "heartbeat_path"), ("health", "state_path"),
                ("geniex_supervisor", "state_path"), ("stability_analysis", "log_path"),
            )),
    )
    return all(checks)


def _read_document(path):
    if (path.is_symlink() or not path.is_file()
            or path.stat().st_size > 65536):
        raise ValueError("Invalid profile file")
    content = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(content, dict):
        raise ValueError("Invalid profile object")
    return content


def inspect(source_path=SOURCE, stage_path=STAGE):
    sound = False
    exact = False
    source_off = False
    stage_off = False
    try:
        source = _read_document(source_path)
        staged = _read_document(stage_path)
        source_off = _config_safe(source)
        stage_off = _config_safe(staged)
        planned = candidate(source)
        actual = _merge_settings(DEFAULT_SETTINGS, staged)
        exact = planned == actual
        validation = validate_settings(actual, require_ventuno_profile=True)
        sound = (source_off and stage_off and exact and
                 attest(actual) and validation.get("valid") is True)
    except (OSError, ValueError, TypeError, KeyError, AttributeError):
        sound = False
    return {
        "status": ("source-only-isolated-stage-contract-passed" if sound
                   else "source-only-stage-contract-denied"),
        "candidate_safe_by_contract": sound,
        "source_profile_all_risk_flags_off": source_off,
        "stage_profile_all_risk_flags_off": stage_off,
        "stage_exactly_matches_reviewed_override": exact,
        "real_audio_authorized": False,
        "production_config_changed": False,
        "test_database_created": False,
        "libraries_installed": False,
        "stt_model_loaded": False,
        "npu_inference_started": False,
        "test_run_approved": False,
    }


def main():
    result = inspect()
    print("MYAI_VOICE_STAGE_CONTRACT_JSON=" + json.dumps(result, sort_keys=True))
    return 0 if result["candidate_safe_by_contract"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
