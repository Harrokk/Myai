"""Read-only physical readiness for Arduino App Lab ASR v2 on VENTUNO Q.

Reads procfs and optional systemd service state only. Never imports Arduino,
opens /dev/snd, captures PCM, selects a microphone, loads Whisper, downloads
models, changes services or grants recording consent. All output is categorical.
"""
from __future__ import annotations

import json
from pathlib import Path
import re
import subprocess

PROC_ASOUND = Path("/proc/asound")
SERVICE_NAMES = ("myai-ventuno.service", "myai-geniex.service")
_CAPTURE = re.compile(
    r"^\s*(\d{1,3})-(\d{1,3}):[^\n]*?\bcapture\s+([1-9]\d{0,3})(?:\s|$)"
)


def usb_capture_devices(proc_root: Path = PROC_ASOUND) -> tuple[tuple[int, int], ...]:
    """Only ALSA capture devices with a USB card usbid marker.

    This is *not* a guarantee that the default Arduino device selector would
    choose the microphone; used only as a fail-closed manual review signal.
    """
    try:
        pcm = proc_root / "pcm"
        if pcm.is_symlink() or not pcm.is_file() or pcm.stat().st_size > 32768:
            return ()
        lines = pcm.read_text(encoding="ascii", errors="replace").splitlines()
    except OSError:
        return ()
    devices: set[tuple[int, int]] = set()
    for line in lines:
        match = _CAPTURE.match(line)
        if not match:
            continue
        card, device = int(match[1]), int(match[2])
        if card > 63 or device > 63:
            continue
        try:
            usbid = proc_root / f"card{card}" / "usbid"
            if (usbid.is_symlink() or not usbid.is_file()
                    or usbid.stat().st_size > 64):
                continue
            identifier = usbid.read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            continue
        # USB VID:PID only; never export even this identifier to public output.
        if re.fullmatch(r"[0-9a-fA-F]{4}:[0-9a-fA-F]{4}", identifier):
            devices.add((card, device))
    return tuple(sorted(devices))


def _read_only_service_active(name: str) -> bool | None:
    if name not in SERVICE_NAMES:
        return None
    try:
        process = subprocess.run(
            ["systemctl", "is-active", "--quiet", name],
            check=False, capture_output=True, timeout=3,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None
    return process.returncode == 0


def inspect(
    proc_root: Path = PROC_ASOUND,
    service_state=None,
) -> dict[str, object]:
    devices = usb_capture_devices(proc_root)
    state_fn = service_state if service_state is not None else _read_only_service_active
    states = tuple(state_fn(name) for name in SERVICE_NAMES)
    # No device identifiers, paths, serial numbers, raw text or service
    # stdout/stderr enter the bounded report.
    if len(devices) == 0:
        category = "no-unique-usb-capture-found"
    elif len(devices) > 1:
        category = "multiple-usb-capture-devices"
    else:
        category = "exactly-one-usb-capture-device"
    if any(value is None for value in states):
        services = "unverified"
    elif all(value is True for value in states):
        services = "both-active"
    elif all(value is False for value in states):
        services = "both-inactive"
    else:
        services = "mixed-state"
    return {
        "status": "metadata-only-completed",
        "usb_capture_category": category,
        "usb_capture_count": min(len(devices), 99),
        "myai_geniex_services": services,
        "whisper_small_installed": "operator-reported-not-locally-verified",
        "microphone_opened": False,
        "recording_performed": False,
        "model_loaded": False,
        "services_modified": False,
        "authorizes_recording": False,
        "authorizes_service_stop": False,
    }


def main() -> int:
    result = inspect()
    print("MYAI_APP_LAB_ASR_V2_PREFLIGHT=" +
          json.dumps(result, sort_keys=True))
    # Inspection success never means permission to record.
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
