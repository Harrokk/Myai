"""Read-only ALSA card 0 / capture 1 access and substream-state inventory.

No arecord execution, device open, stream capture, mixer write, package
installation, sound payload inspection or production MyAI service changes.
Reports only booleans and bounded states, never owner IDs or device labels.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path

DEVICE = Path("/dev/snd/pcmC0D1c")
SUBSTREAM = Path("/proc/asound/card0/pcm1c/sub0")
MAX_METADATA_BYTES = 4096


def status_category(path: Path) -> str:
    try:
        if path.is_symlink() or not path.is_file():
            return "unavailable"
        with path.open("rb") as stream:
            payload = stream.read(MAX_METADATA_BYTES + 1)
        if len(payload) > MAX_METADATA_BYTES:
            return "unavailable"
        lines = payload.decode("utf-8", errors="replace").lower().splitlines()
    except OSError:
        return "unavailable"
    if len(lines) == 1 and lines[0].strip() == "closed":
        return "closed"
    for line in lines:
        if line.lstrip().startswith("state:"):
            value = line.split(":", 1)[1].strip().upper()
            if value in {"OPEN", "SETUP", "PREPARED", "RUNNING", "XRUN",
                         "DRAINING", "PAUSED", "SUSPENDED", "DISCONNECTED"}:
                return value.lower()
    return "unknown"


def inspect_capture_permissions(
    device: Path = DEVICE, substream: Path = SUBSTREAM,
) -> dict[str, object]:
    result: dict[str, object] = {
        "status": "inconclusive-capture-device-access",
        "capture_node_exists": False,
        "capture_node_character_device": False,
        "capture_node_read_access": False,
        "capture_node_write_access": False,
        "capture_substream_state": "unavailable",
        "alsa_hw_params_state": "unavailable",
        "mic_stream_opened": False,
        "recording_performed": False,
        "mixer_settings_changed": False,
        "production_services_changed": False,
    }
    try:
        if device.is_symlink():
            return result
        mode = device.stat().st_mode
    except OSError:
        return result
    result["capture_node_exists"] = True
    if not stat.S_ISCHR(mode):
        result["status"] = "reject-capture-node-not-character-device"
        return result
    result["capture_node_character_device"] = True
    # os.access checks permissions without opening /dev/snd.
    result["capture_node_read_access"] = os.access(device, os.R_OK)
    result["capture_node_write_access"] = os.access(device, os.W_OK)
    result["capture_substream_state"] = status_category(substream / "status")
    result["alsa_hw_params_state"] = (
        "closed" if status_category(substream / "hw_params") == "closed"
        else "present-or-inconclusive"
    )
    result["status"] = (
        "capture-node-not-accessible-by-runner"
        if not result["capture_node_read_access"] or
           not result["capture_node_write_access"]
        else "capture-node-permissions-appear-available"
    )
    # Successful os.access and ALSA node presence do not establish that
    # capture can start, a microphone is physically connected, or a codec
    # supports 16 kHz mono S16_LE.
    return result


def main() -> int:
    report = inspect_capture_permissions()
    print("VENTUNO read-only ALSA 0:1 permission/state:",
          json.dumps(report, sort_keys=True))
    print("No ALSA capture or playback device opened.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
