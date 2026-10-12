"""Read-only ALSA mixer capture-state probe for VENTUNO Q.

Reads only "amixer -c 0 scontents"; does not execute capture, playback,
set controls, log mixer labels, persist audio, or change system services.
The summary is deliberately restricted to predefined boolean/count fields.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess

TIMEOUT_SECONDS = 5
MAX_RESPONSE_BYTES = 64 * 1024


def parse_capture_controls(raw: bytes) -> dict[str, int]:
    if not isinstance(raw, bytes) or len(raw) > MAX_RESPONSE_BYTES:
        raise ValueError("invalid-mixer-output")
    lines = raw.decode("utf-8", errors="replace").splitlines()
    total = 0
    switch_on = switch_off = volume_zero = volume_nonzero = 0
    block: list[str] = []

    def consume(section: list[str]) -> tuple[int, int, int, int, int]:
        if not section:
            return (0, 0, 0, 0, 0)
        metadata = "\n".join(section)
        capability = re.search(
            r"(?m)^\s*Capabilities:\s*[^\n]*\b(?:cswitch|cvolume|cswitch-joined)\b",
            metadata,
        )
        if not capability and not re.search(r"(?m)^\s*Capture channels:", metadata):
            return (0, 0, 0, 0, 0)
        on = off = zero = nonzero = 0
        for item in section:
            if not re.search(r":\s*Capture\b", item):
                continue
            states = re.findall(r"\[(on|off)\]", item, flags=re.IGNORECASE)
            on += sum(s.lower() == "on" for s in states)
            off += sum(s.lower() == "off" for s in states)
            percentages = re.findall(r"\[(\d{1,3})%\]", item)
            zero += sum(int(p) == 0 for p in percentages)
            nonzero += sum(int(p) > 0 for p in percentages)
        return (1, on, off, zero, nonzero)

    for line in lines:
        if line.startswith("Simple mixer control "):
            n, on, off, zero, nonzero = consume(block)
            total += n
            switch_on += on
            switch_off += off
            volume_zero += zero
            volume_nonzero += nonzero
            block = [line]
        elif block:
            block.append(line)
    n, on, off, zero, nonzero = consume(block)
    total += n
    switch_on += on
    switch_off += off
    volume_zero += zero
    volume_nonzero += nonzero
    return {
        "capture_controls": total,
        "capture_switch_on_reports": switch_on,
        "capture_switch_off_reports": switch_off,
        "capture_volume_zero_reports": volume_zero,
        "capture_volume_nonzero_reports": volume_nonzero,
    }


def inspect_mixer() -> dict[str, object]:
    result: dict[str, object] = {
        "status": "inconclusive-mixer-metadata",
        "mixer_query_completed": False,
        "capture_controls": 0,
        "capture_switch_on_reports": 0,
        "capture_switch_off_reports": 0,
        "capture_volume_zero_reports": 0,
        "capture_volume_nonzero_reports": 0,
        "recording_performed": False,
        "playback_performed": False,
        "mixer_controls_changed": False,
        "production_services_changed": False,
        "physical_microphone_verified": False,
    }
    tool = shutil.which("amixer")
    if tool is None:
        result["status"] = "amixer-unavailable"
        return result
    try:
        process = subprocess.run(
            [tool, "-c", "0", "scontents"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        result["status"] = "mixer-query-failed"
        return result
    if process.returncode != 0:
        result["status"] = "mixer-query-failed"
        return result
    try:
        parsed = parse_capture_controls(process.stdout)
    except ValueError:
        result["status"] = "mixer-output-unavailable"
        return result
    result["mixer_query_completed"] = True
    result.update(parsed)
    if not parsed["capture_controls"]:
        result["status"] = "no-capture-controls-exposed"
    elif not any((
        parsed["capture_switch_on_reports"],
        parsed["capture_switch_off_reports"],
        parsed["capture_volume_zero_reports"],
        parsed["capture_volume_nonzero_reports"],
    )):
        result["status"] = "capture-controls-without-level-readings"
    elif parsed["capture_switch_off_reports"]:
        result["status"] = "some-capture-switches-report-off"
    elif parsed["capture_volume_zero_reports"]:
        result["status"] = "some-capture-volumes-report-zero"
    else:
        result["status"] = "capture-control-metadata-readable"
    return result


def main() -> int:
    print("VENTUNO read-only ALSA mixer state:",
          json.dumps(inspect_mixer(), sort_keys=True))
    print("No microphone capture, playback or ALSA mixer modification performed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
