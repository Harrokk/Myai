"""VENTUNO Q local Ollama inventory; no model loads or machine modifications.

Only reads a local executable path and two *loopback* HTTP endpoints.
Never calls chat/generate/pull, downloads packages, starts a service,
alters production config, or records/plays audio. All output is bounded
and contains no source response bodies or private model names.
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
from urllib.error import HTTPError, URLError
from urllib.request import urlopen

from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes
from pathlib import Path

API_BASE = "http://127.0.0.1:11434"
RECOMMENDED_MODEL = "qwen3:0.6b"
MAX_HTTP_BODY = 64 * 1024
MIN_SPARE_RAM_KIB = 2 * 1024 * 1024
MIN_SPARE_DISK_BYTES = 2 * 1024 * 1024 * 1024
USER_LOCAL_BINARY = Path("/home/arduino/.local/opt/myai-ollama/v0.34.0/bin/ollama")


def _local_json(path: str) -> dict[str, object] | None:
    if path not in ("/api/version", "/api/tags"):
        return None
    try:
        with urlopen(API_BASE + path, timeout=2) as response:
            body = response.read(MAX_HTTP_BODY + 1)
        if len(body) > MAX_HTTP_BODY:
            return None
        result = json.loads(body)
        return result if isinstance(result, dict) else None
    except (HTTPError, URLError, OSError, TimeoutError,
            ValueError, json.JSONDecodeError):
        return None


def inspect_ollama(
    *,
    machine: str | None = None,
    available_mem_kib: int | None = None,
    free_disk_bytes: int | None = None,
    user_local_binary: Path = USER_LOCAL_BINARY,
) -> dict[str, object]:
    machine = platform.machine() if machine is None else machine
    if available_mem_kib is None:
        available_mem_kib = mem_available_kib()
    if free_disk_bytes is None:
        free_disk_bytes = disk_free_bytes(Path("/"))
    binary = shutil.which("ollama")
    try:
        staged_exists = (
            not user_local_binary.is_symlink()
            and user_local_binary.is_file()
            and os.access(user_local_binary, os.X_OK)
        )
    except (OSError, ValueError):
        staged_exists = False
    version = _local_json("/api/version")
    tags = _local_json("/api/tags") if version is not None else None
    installed = bool(binary) or staged_exists
    server = isinstance(version, dict) and isinstance(version.get("version"), str)
    models = tags.get("models") if isinstance(tags, dict) else None
    model_ready = (isinstance(models, list) and any(
        isinstance(entry, dict)
        and entry.get("name") == RECOMMENDED_MODEL
        for entry in models[:100]
    ))
    report: dict[str, object] = {
        "status": "ready-for-separate-ollama-test" if installed and server and model_ready
                  else "ollama-api-ready-no-small-model" if installed and server
                  else "ollama-binary-present-api-unavailable" if installed
                  else "ollama-not-installed",
        "arm64": machine.lower() in ("arm64", "aarch64"),
        "ollama_binary_present": installed,
        "loopback_ollama_api_ready": server,
        "test_model_already_downloaded": bool(model_ready),
        "available_ram_mib": round(available_mem_kib / 1024)
                             if type(available_mem_kib) is int else None,
        "disk_available_mib": round(free_disk_bytes / (1024 * 1024))
                              if type(free_disk_bytes) is int else None,
        "spare_memory_for_small_model": (
            type(available_mem_kib) is int and
            available_mem_kib >= MIN_SPARE_RAM_KIB
        ),
        "spare_disk_for_staging": (
            type(free_disk_bytes) is int and
            free_disk_bytes >= MIN_SPARE_DISK_BYTES
        ),
        "ollama_started": False,
        "model_loaded": False,
        "files_changed": False,
        "geniex_touched": False,
        "production_voice_touched": False,
    }
    return report


def main() -> int:
    result = inspect_ollama()
    print("VENTUNO read-only Ollama readiness:", json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
