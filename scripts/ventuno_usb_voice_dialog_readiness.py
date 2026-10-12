"""Read-only VENTUNO Q readiness for a future consented USB voice dialogue.

No microphone stream, playback, model load, package installation, network
request, audio recording, service restart or config write. The 8 GiB
Whisper CPU benchmark gate is unchanged and enforced before live dialogue.
"""
from __future__ import annotations

import json
import platform
from pathlib import Path
from typing import Any

from scripts.ventuno_usb_audio_inventory import inventory_usb_audio
from scripts.ventuno_voice_wheel_staging import mem_available_kib, disk_free_bytes
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MIN_MEM_AVAILABLE_KIB, MIN_DISK_AVAILABLE_BYTES,
)

PROFILE = Path("/home/arduino/MyAI/config/profiles/ventuno_q.json")
ALSA_PAIR = [1, 0]
CARD = 1


def summarize_readiness(
    *,
    machine: str, mem_kib: int | None, free_disk_bytes: int | None,
    usb: dict[str, Any], voice: object, services_active: bool,
) -> dict[str, object]:
    """Return only bounded booleans/numbers; never device names or labels."""
    capture = any(
        isinstance(entry, dict) and entry.get("pair") == ALSA_PAIR
        and entry.get("character_device") is True
        and entry.get("accessible") is True
        for entry in usb.get("capture_device_nodes", [])
    )
    playback = any(
        isinstance(entry, dict) and entry.get("pair") == ALSA_PAIR
        and entry.get("character_device") is True
        and entry.get("accessible") is True
        for entry in usb.get("playback_device_nodes", [])
    )
    usb_ok = (
        CARD in usb.get("usb_audio_cards", [])
        and ALSA_PAIR in usb.get("usb_capture_pairs", [])
        and ALSA_PAIR in usb.get("usb_playback_pairs", [])
        and capture and playback
    )
    config_safe = (
        isinstance(voice, dict)
        and all(voice.get(flag) is not True for flag in (
            "enabled", "tts_enabled", "handsfree_enabled",
        ))
    )
    arm = machine.lower() in ("aarch64", "arm64")
    mem_ready = (
        type(mem_kib) is int
        and mem_kib >= MIN_MEM_AVAILABLE_KIB
    )
    disk_ready = (
        type(free_disk_bytes) is int
        and free_disk_bytes >= MIN_DISK_AVAILABLE_BYTES
    )
    report: dict[str, object] = {
        "status": "blocked",
        "arm64": arm,
        "services_active": services_active is True,
        "production_voice_disabled": config_safe,
        "usb_capture_and_playback_1_0_accessible": usb_ok,
        "ram_available_mib": round(mem_kib / 1024) if type(mem_kib) is int else None,
        "ram_required_mib": MIN_MEM_AVAILABLE_KIB // 1024,
        "disk_available_mib": (
            round(free_disk_bytes / (1024 * 1024))
            if type(free_disk_bytes) is int else None
        ),
        "disk_required_mib": MIN_DISK_AVAILABLE_BYTES // (1024 * 1024),
        "ram_gate_passed": mem_ready,
        "disk_gate_passed": disk_ready,
        "microphone_opened": False,
        "speaker_opened": False,
        "model_loaded": False,
        "production_changed": False,
        "physical_dialogue_attempted": False,
    }
    if not arm:
        report["status"] = "blocked-architecture"
    elif services_active is not True:
        report["status"] = "blocked-inactive-services"
    elif not config_safe:
        report["status"] = "blocked-active-voice-or-invalid-config"
    elif not usb_ok:
        report["status"] = "blocked-usb-reenumerated-or-inaccessible"
    elif not mem_ready:
        report["status"] = "blocked-whisper-8gib-memory-reserve"
    elif not disk_ready:
        report["status"] = "blocked-temporary-staging-disk-reserve"
    else:
        report["status"] = "ready-for-separate-consented-dialogue-test"
    return report


def check_services() -> bool:
    import subprocess
    try:
        for service in ("myai-ventuno.service", "myai-geniex.service"):
            result = subprocess.run(
                ["systemctl", "is-active", "--quiet", service],
                check=False, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, timeout=4,
            )
            if result.returncode != 0:
                return False
        return True
    except (OSError, subprocess.TimeoutExpired):
        return False


def inspect(
    *,
    profile_path: Path = PROFILE,
    disk_root: Path = Path("/"),
) -> dict[str, object]:
    voice: object = None
    try:
        if not profile_path.is_symlink() and profile_path.is_file():
            if profile_path.stat().st_size <= 64 * 1024:
                profile = json.loads(profile_path.read_text(encoding="utf-8"))
                if isinstance(profile, dict):
                    voice = profile.get("voice")
    except (OSError, ValueError, TypeError):
        pass
    return summarize_readiness(
        machine=platform.machine(),
        mem_kib=mem_available_kib(),
        free_disk_bytes=disk_free_bytes(disk_root),
        usb=inventory_usb_audio(),
        voice=voice,
        services_active=check_services(),
    )


def main() -> int:
    report = inspect()
    print("VENTUNO USB voice read-only readiness:",
          json.dumps(report, sort_keys=True))
    print("No microphone, speaker, model, recording or production change.")
    # Report a measured no-go as a successful diagnostic operation.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
