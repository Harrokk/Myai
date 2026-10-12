"""Read-only ALSA capture routing inventory for VENTUNO Q.

This script NEVER opens an audio stream or records microphone data.
It inspects only bounded /proc/asound/pcm metadata and the documented
listing-only ALSA flags 'arecord -l' and 'arecord -L'. No device names,
user configuration paths or ALSA stderr are printed. Presence of a PCM
is NOT proof it can record S16_LE at 16 kHz from the default device.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path

MAX_PROC_BYTES = 16 * 1024
MAX_CLI_BYTES = 64 * 1024
TIMEOUT_SECONDS = 5
MAX_DEVICES = 16
ALIASES = ("default", "sysdefault", "plughw", "hw", "pulse", "pipewire")


def proc_pcm_inventory(path: Path) -> dict[str, object]:
    out: dict[str, object] = {
        "proc_pcm_readable": False,
        "capture_pcm_hardware_pairs": [],
        "playback_pcm_hardware_pairs": [],
        "proc_pcm_scan_truncated": False,
    }
    try:
        if path.is_symlink() or not path.is_file():
            return out
        with path.open("rb") as handle:
            raw = handle.read(MAX_PROC_BYTES + 1)
        if len(raw) > MAX_PROC_BYTES:
            out["proc_pcm_scan_truncated"] = True
            return out
        text = raw.decode("utf-8", errors="replace")
    except OSError:
        return out
    capture: list[list[int]] = []
    playback: list[list[int]] = []
    for line in text.splitlines():
        match = re.match(r"^\s*([0-9]{2})-([0-9]{2}):", line)
        if match is None:
            continue
        pair = [int(match[1]), int(match[2])]
        if re.search(r"\bcapture\s+[1-9][0-9]*\b", line):
            if pair not in capture and len(capture) < MAX_DEVICES:
                capture.append(pair)
        if re.search(r"\bplayback\s+[1-9][0-9]*\b", line):
            if pair not in playback and len(playback) < MAX_DEVICES:
                playback.append(pair)
    out.update({
        "proc_pcm_readable": True,
        "capture_pcm_hardware_pairs": capture,
        "playback_pcm_hardware_pairs": playback,
    })
    return out


def classify_arecord_list(stdout: bytes, mode: str) -> dict[str, object]:
    if mode not in ("-l", "-L"):
        raise ValueError("only-read-only-alsa-listing-options")
    out: dict[str, object] = {
        "parse_complete": False,
        "capture_hardware_pairs": [],
        "aliases_present": [],
    }
    if not isinstance(stdout, bytes) or len(stdout) > MAX_CLI_BYTES:
        return out
    text = stdout.decode("utf-8", errors="replace")
    if mode == "-l":
        pairs = []
        for line in text.splitlines():
            match = re.search(
                r"\bcard\s+([0-9]{1,3}):.*?\bdevice\s+([0-9]{1,3}):",
                line, re.IGNORECASE,
            )
            if match:
                pair = [int(match[1]), int(match[2])]
                if pair not in pairs and len(pairs) < MAX_DEVICES:
                    pairs.append(pair)
        out["capture_hardware_pairs"] = pairs
    else:
        # Top-level aliases are unindented tokens. Do not leak their labels.
        tops = {
            line.strip().lower()
            for line in text.splitlines()
            if line and not line[0].isspace()
        }
        out["aliases_present"] = [name for name in ALIASES if name in tops]
    out["parse_complete"] = True
    return out


def list_alsa_capture(*, tool: str | None = None,
                      proc_pcm: Path = Path("/proc/asound/pcm")) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "inconclusive-alsa-route",
        "arecord_present": False,
        "arecord_list_hardware_success": False,
        "arecord_list_pcm_aliases_success": False,
        "alsa_default_alias_listed": False,
        "alsa_capture_hardware_pairs": [],
        "alsa_pcm_aliases_present": [],
        "audio_stream_opened": False,
        "microphone_recorded": False,
        "services_changed": False,
        "production_config_modified": False,
    }
    report.update(proc_pcm_inventory(proc_pcm))
    if tool is None:
        tool = shutil.which("arecord")
    report["arecord_present"] = bool(tool)
    if not tool:
        report["status"] = "arecord-not-installed"
        return report
    for flag in ("-l", "-L"):
        try:
            p = subprocess.run(
                [tool, flag], capture_output=True, check=False,
                timeout=TIMEOUT_SECONDS,
            )
        except (subprocess.TimeoutExpired, OSError):
            continue
        if p.returncode != 0:
            continue
        classified = classify_arecord_list(p.stdout, flag)
        if not classified["parse_complete"]:
            continue
        if flag == "-l":
            report["arecord_list_hardware_success"] = True
            report["alsa_capture_hardware_pairs"] = classified["capture_hardware_pairs"]
        else:
            report["arecord_list_pcm_aliases_success"] = True
            report["alsa_pcm_aliases_present"] = classified["aliases_present"]
            report["alsa_default_alias_listed"] = (
                "default" in classified["aliases_present"]
            )
    if report["arecord_list_hardware_success"] and report["proc_pcm_readable"]:
        report["status"] = "alsa-listing-observed-capture-routing-unverified"
    return report


def main() -> int:
    result = list_alsa_capture()
    print("VENTUNO read-only ALSA capture routing:", json.dumps(result, sort_keys=True))
    print("No recording, microphone open, loudspeaker output, settings or services changed.")
    return 0 if result["arecord_list_hardware_success"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
