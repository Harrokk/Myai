"""Opt-in exactly two-second USB microphone diagnostic on VENTUNO Q.

Does not open a microphone unless both flags are supplied and fresh
ALSA metadata confirms that card 1 / device 0 is an accessible USB
capture PCM. Never stores audio, transcribes, streams or plays it.
"""
from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess

from scripts.ventuno_microphone_smoke import (
    BYTES_EXPECTED, MAX_OUTPUT_BYTES, TIMEOUT_SECONDS,
    classify_alsa_error, evaluate_pcm,
)
from scripts.ventuno_usb_audio_inventory import inventory_usb_audio

APPROVED_DEVICE = "plughw:1,0"
APPROVED_PAIR = [1, 0]


def usb_microphone_capture(*, record_2s: bool = False,
                           consent: bool = False,
                           device: str = APPROVED_DEVICE) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "not-authorized",
        "capture_executed": False,
        "audio_saved_to_disk": False,
        "audio_transmitted": False,
        "speech_transcribed": False,
        "speaker_playback_started": False,
        "production_services_modified": False,
    }
    if not (record_2s and consent):
        return report
    if platform.machine().lower() not in ("arm64", "aarch64"):
        report["status"] = "reject-non-arm64"
        return report
    if device != APPROVED_DEVICE:
        report["status"] = "reject-unapproved-target"
        return report
    inventory = inventory_usb_audio()
    if (inventory.get("status") not in (
            "usb-capture-and-playback-pcm-detected",
            "usb-capture-only-pcm-detected",
        ) or APPROVED_PAIR not in inventory.get("usb_capture_pairs", [])
        or 1 not in inventory.get("usb_audio_cards", [])):
        report["status"] = "reject-usb-device-changed-or-missing"
        return report
    nodes = inventory.get("capture_device_nodes", [])
    if not any(
        isinstance(n, dict) and n.get("pair") == APPROVED_PAIR
        and n.get("character_device") is True and n.get("accessible") is True
        for n in nodes
    ):
        report["status"] = "reject-usb-capture-node-not-accessible"
        return report

    arecord = shutil.which("arecord")
    if not arecord:
        report["status"] = "arecord-unavailable"
        return report
    argv = [
        arecord, "--quiet", "--device=" + APPROVED_DEVICE,
        "--format=S16_LE", "--rate=16000", "--channels=1",
        "--duration=2", "--type=raw", "-",
    ]
    try:
        process = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        report["status"] = "capture-timeout"
        return report
    except OSError:
        report["status"] = "capture-launch-error"
        return report

    report["capture_executed"] = True
    if process.returncode != 0:
        report["status"] = "alsa-capture-nonzero"
        report["alsa_error_category"] = classify_alsa_error(process.stderr)
        return report
    if len(process.stdout) > MAX_OUTPUT_BYTES:
        report["status"] = "capture-over-size"
        return report
    if len(process.stdout) != BYTES_EXPECTED:
        report["status"] = "capture-incomplete"
        report["bytes_received"] = len(process.stdout)
        return report
    report.update(evaluate_pcm(process.stdout))
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-2s", action="store_true")
    parser.add_argument("--consent-to-record", action="store_true")
    parser.add_argument("--device", default=APPROVED_DEVICE,
                        choices=(APPROVED_DEVICE,))
    args = parser.parse_args()
    report = usb_microphone_capture(
        record_2s=args.record_2s,
        consent=args.consent_to_record,
        device=args.device,
    )
    print("VENTUNO USB microphone in-memory diagnostic:",
          json.dumps(report, sort_keys=True))
    return 0 if report["status"] in (
        "not-authorized", "microphone-signal-measured",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
