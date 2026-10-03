import json
from copy import deepcopy
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_SETTINGS_PATH = PROJECT_ROOT / "config" / "settings.json"

DEFAULT_SETTINGS = {
    "ollama": {
        "url": "http://localhost:11434/api/chat",
        "model": "qwen3:8b",
    },
    "vision": {
        "enabled": False,
        "url": "http://localhost:11434/api/chat",
        "model": "",
        "timeout_seconds": 120,
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
    },
    "conversation": {
        "max_turns": 6,
    },
    "hardware_watch": {
        "enabled": True,
        "interval_seconds": 10,
    },
    "trusted_terminals": {
        "enabled": False,
        "connect_rssi": -60,
        "disconnect_rssi": -75,
        "terminals": [],
    },
    "assistant": {
        "name": "MyAI v2",
        "engine": "Ollama",
        "gpu": "NVIDIA RTX 3060 12 GB",
        "memory_label": "SQLite",
        "future_target": "Raspberry Pi 5 B",
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


def load_settings(path=None):
    """Ladda konfiguration och fyll i saknade värden med säkra standarder."""
    settings_path = Path(path) if path else DEFAULT_SETTINGS_PATH

    if not settings_path.exists():
        return deepcopy(DEFAULT_SETTINGS)

    with settings_path.open("r", encoding="utf-8") as file:
        loaded = json.load(file)

    if not isinstance(loaded, dict):
        raise ValueError("Konfigurationsfilen måste innehålla ett JSON-objekt.")

    return _merge_settings(DEFAULT_SETTINGS, loaded)
