import json
import os
from copy import deepcopy
from pathlib import Path

from core.config_schema import (
    CURRENT_CONFIG_SCHEMA_VERSION,
    migrate_config_document,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "schema_version": CURRENT_CONFIG_SCHEMA_VERSION,
    "llm": {
        "provider": "ollama",
        "fallback": {
            "enabled": False,
            "provider": "geniex",
            "model": "",
            "health_aware": {
                "enabled": False,
                "failure_threshold": 3,
                "recovery_success_threshold": 3,
            },
        },
    },
    "ollama": {
        "url": "http://localhost:11434/api/chat",
        "model": "qwen3:8b",
    },
    "geniex": {
        "base_url": "http://127.0.0.1:18181/v1",
        "model": "ai-hub-models/Qwen3-4B-Instruct-2507",
        "api_key": "geniex",
        "max_tokens": 256,
        "temperature": 0.4,
        "enable_think": False,
        "stream_enabled": True,
    },
    "geniex_supervisor": {
        "enabled": False,
        "health_timeout_seconds": 3.0,
        "failure_threshold": 3,
        "restart_enabled": False,
        "restart_command": [],
        "restart_timeout_seconds": 30.0,
        "restart_cooldown_seconds": 60.0,
        "max_restart_attempts": 3,
        "state_path": "runtime/geniex_health.json",
        "state_stale_seconds": 30.0,
    },
    "health": {
        "state_path": "runtime/myai_health.json",
        "state_stale_seconds": 60.0,
    },
    "diagnostics": {
        "runtime_stale_seconds": 30.0,
    },
    "logging": {
        "jsonl_max_bytes": 5_000_000,
        "jsonl_backups": 5,
    },
    "error_logging": {
        "enabled": True,
        "path": "runtime/errors.jsonl",
        "max_message_chars": 500,
        "recent_limit": 10,
    },
    "audit_logging": {
        "enabled": True,
        "require_for_writes": True,
        "path": "runtime/audit.jsonl",
        "max_detail_chars": 200,
        "recent_limit": 20,
    },
    "stability_analysis": {
        "log_path": "runtime/ventuno_stability.jsonl",
        "max_records": 10_000,
        "target_hours": 72.0,
        "trend_fraction": 0.25,
        "latency_degradation_ratio": 1.25,
    },
    "deployment_lock": {
        "required": False,
        "lock_path": "config/ventuno_stack_lock.json",
    },
    "selfdev": {
        "enabled": False,
        "workspace_root": "runtime/selfdev",
        "promotion_enabled": False,
        "require_bubblewrap": True,
        "verification_timeout_seconds": 300.0,
    },
    "vision": {
        "enabled": False,
        "provider": "ollama",
        "url": "http://localhost:11434/api/chat",
        "model": "",
        "timeout_seconds": 120,
        "max_tokens": 256,
        "temperature": 0.2,
    },
    "ventuno": {
        "enabled": False,
        "rpc_enabled": False,
        "rpc_write_enabled": False,
        "rpc_connect_timeout_seconds": 5.0,
        "rpc_call_timeout_seconds": 5.0,
        "rpc_allowed_read_methods": [],
        "rpc_allowed_write_methods": [],
    },
    "voice": {
        "enabled": False,
        "tts_enabled": False,
        "microphone_provider": "sounddevice",
        "vad_provider": "webrtcvad",
        "stt_provider": "faster_whisper",
        "backup_stt_provider": "faster_whisper",
        "tts_provider": "pyttsx3",
        "sample_rate": 16000,
        "channels": 1,
        "sample_width": 2,
        "frame_ms": 20,
        "input_device": None,
        "vad_aggressiveness": 2,
        "stt_model": "small",
        "stt_device": "auto",
        "stt_compute_type": "default",
        "stt_language": "sv",
        "backup_stt_models": [],
        "tts_rate": 180,
        "tts_volume": 1.0,
        "tts_voice_id": "",
        "tts_async": True,
        "tts_stop_timeout_seconds": 2.0,
        "llm_streaming_enabled": False,
        "stream_tts_min_chars": 24,
        "stream_tts_max_chars": 220,
        "stream_tts_stop_timeout_seconds": 2.0,
        "release_microphone_during_inference": False,
        "model_handoff_delay_seconds": 0.0,
        "release_stt_before_model": False,
        "semantic_consensus_enabled": False,
        "semantic_consensus_for_high_risk": False,
        "semantic_consensus_min_confidence": 0.85,
        "redundancy_enabled": True,
        "redundancy_when_confidence_missing": False,
        "primary_confidence_threshold": 0.72,
        "consensus_similarity_threshold": 0.62,
        "redundant_transcript_count": 3,
        "vad_start_speech_frames": 2,
        "vad_end_silence_frames": 3,
        "vad_max_frames": 500,
        "session_max_wait_frames": 1500,
        "handsfree_enabled": False,
        "handsfree_max_wait_frames": 1500,
        "handsfree_stop_timeout_seconds": 3.0,
        "echo_guard_enabled": True,
        "echo_guard_window_seconds": 5.0,
        "echo_guard_similarity_threshold": 0.78,
        "echo_guard_min_words": 3,
        "echo_guard_for_high_risk": False,
        "high_risk_confirmation_enabled": True,
        "high_risk_confirmation_window_seconds": 15.0,
        "high_risk_confirmation_min_confidence": 0.80,
        "high_risk_confirmation_transcript_count": 3,
    },
    "camera": {
        "default_index": 0,
        "capture_dir": "runtime/captures",
        "video_dir": "runtime/video",
        "video_duration_seconds": 5,
        "video_fps": 10,
        "video_frame_dir": "runtime/video_frames",
        "video_sample_count": 5,
        "stream_enabled": False,
        "stream_duration_seconds": 5,
        "stream_fps": 2,
        "stream_max_frames": 10,
    },
    "location": {
        "enabled": False,
        "source": "gps_serial",
        "serial_port": "",
        "baudrate": 9600,
        "timeout_seconds": 1,
        "max_lines": 20,
    },
    "research": {
        "candidate_limit": 5,
        "top_n": 3,
        "min_source_reliability": 40,
        "min_information_confidence": 40,
        "min_relevance": 40,
        "warning_penalty_each": 5,
        "max_warning_penalty": 20,
        "weights": {
            "relevance": 0.30,
            "source_reliability": 0.30,
            "information_confidence": 0.30,
            "practicality": 0.10,
        },
    },
    "internet": {
        "enabled": False,
        "provider": "searxng",
        "searxng_url": "http://localhost:8080",
        "timeout_seconds": 15,
        "max_results": 5,
        "language": "sv-SE",
        "safesearch": 1,
        "max_page_bytes": 1_000_000,
        "max_page_chars": 20_000,
        "max_redirects": 5,
    },
    "fx": {
        "enabled": False,
        "provider": "ecb",
        "ecb_url": (
            "https://www.ecb.europa.eu/stats/eurofxref/"
            "eurofxref-daily.xml"
        ),
        "target_currency": "SEK",
        "max_age_days": 7,
    },
    "weather": {
        "enabled": False,
        "provider": "open_meteo",
        "geocoding_url": (
            "https://geocoding-api.open-meteo.com/v1/search"
        ),
        "forecast_url": (
            "https://api.open-meteo.com/v1/forecast"
        ),
        "default_location": "",
        "language": "sv",
        "forecast_days": 3,
    },
    "files": {
        "enabled": True,
        "workspace_root": "runtime/workspace",
        "write_enabled": False,
        "max_read_chars": 20_000,
        "max_list_entries": 100,
        "allowed_write_extensions": [
            ".txt",
            ".md",
            ".csv",
            ".json",
        ],
    },
    "excel": {
        "enabled": True,
        "write_enabled": False,
        "max_rows_read": 100,
        "default_sheet": "Data",
    },
    "memory": {
        "database": "memory.db",
        "max_search_results": 10,
        "auto_assess_enabled": True,
        "auto_save_enabled": True,
        "auto_save_threshold": 80,
        "review_threshold": 55,
        "lifecycle_enabled": True,
        "auto_supersede_explicit_updates": True,
        "conflict_similarity_threshold": 0.65,
        "supersede_similarity_threshold": 0.85,
        "max_conflict_scan": 200,
        "stale_after_days": 0,
    },
    "conversation": {
        "max_turns": 6,
    },
    "runtime": {
        "require_preflight": False,
        "heartbeat_path": "runtime/myai_runtime.json",
        "heartbeat_interval_seconds": 10.0,
        "shutdown_timeout_seconds": 10.0,
    },
    "hardware_watch": {
        "enabled": True,
        "interval_seconds": 10,
    },
    "trusted_terminals": {
        "enabled": False,
        "connect_rssi": -60,
        "disconnect_rssi": -75,
        "scan_interval_seconds": 5.0,
        "scan_timeout_seconds": 5.0,
        "connect_confirm_scans": 2,
        "disconnect_confirm_scans": 3,
        "auto_execute": False,
        "connector_provider": "none",
        "connector_timeout_seconds": 10.0,
        "require_service_uuid": True,
        "terminals": [],
    },
    "assistant": {
        "name": "MyAI v2",
        "engine": "Local LLM provider",
        "gpu": "NVIDIA RTX 3060 12 GB",
        "memory_label": "SQLite",
        "current_platform": "Windows-dator",
        "future_target": "Arduino VENTUNO Q / Dragonwing IQ-8275",
    },
}


def _merge_settings(defaults, overrides):
    result = deepcopy(defaults)

    for key, value in overrides.items():
        if (
            key in result
            and isinstance(result[key], dict)
            and isinstance(value, dict)
        ):
            result[key] = _merge_settings(result[key], value)
        else:
            result[key] = value

    return result


def _settings_path(path=None):
    if path is not None:
        return Path(path)

    configured = os.environ.get(
        "MYAI_SETTINGS",
        "",
    ).strip()

    if configured:
        candidate = Path(configured)

        if not candidate.is_absolute():
            candidate = (
                PROJECT_ROOT
                / candidate
            )

        return candidate

    return DEFAULT_SETTINGS_PATH


def load_settings_with_metadata(
    path=None,
):
    """Load settings with in-memory schema migration and provenance metadata."""

    settings_path = _settings_path(
        path
    )

    if not settings_path.exists():
        return {
            "settings": deepcopy(
                DEFAULT_SETTINGS
            ),
            "metadata": {
                "source_path": str(
                    settings_path
                ),
                "source_exists": False,
                "source_version": (
                    CURRENT_CONFIG_SCHEMA_VERSION
                ),
                "effective_version": (
                    CURRENT_CONFIG_SCHEMA_VERSION
                ),
                "migration_changed": False,
                "migration_steps": [],
            },
        }

    with settings_path.open(
        "r",
        encoding="utf-8",
    ) as file:
        loaded = json.load(
            file
        )

    migration = migrate_config_document(
        loaded
    )
    effective = _merge_settings(
        DEFAULT_SETTINGS,
        migration[
            "document"
        ],
    )

    return {
        "settings": effective,
        "metadata": {
            "source_path": str(
                settings_path
            ),
            "source_exists": True,
            "source_version": migration[
                "source_version"
            ],
            "effective_version": migration[
                "effective_version"
            ],
            "migration_changed": migration[
                "changed"
            ],
            "migration_steps": list(
                migration[
                    "steps"
                ]
            ),
        },
    }


def load_settings(path=None):
    """Ladda konfiguration och migrera äldre schema endast i minnet."""

    return load_settings_with_metadata(
        path
    )[
        "settings"
    ]
