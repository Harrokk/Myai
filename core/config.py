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
    "gps": {
        "enabled": False,
        "port": "",
        "baudrate": 9600,
        "timeout_seconds": 2,
        "max_lines": 20,
    },
    "internet": {
        "enabled": False,
        "provider": "searxng",
        "searxng_url": "",
        "timeout_seconds": 15,
        "max_results": 5,
        "language": "sv-SE",
        "max_page_bytes": 1_000_000,
        "max_page_chars": 20_000,
        "max_redirects": 5,
    },
    "research": {
        "candidate_limit": 5,
        "top_results": 3,
        "deep_verification_enabled": True,
        "deep_blend": 0.40,
        "conflict_penalty": 10.0,
        "conflict_relative_tolerance": 0.05,
        "weights": {
            "relevance": 0.40,
            "source_reliability": 0.35,
            "information_confidence": 0.25,
        },
    },
    "shopping": {
        "top_results": 3,
        "min_seller_reliability": 50.0,
        "max_offers": 20,
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
