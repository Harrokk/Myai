"""Opt-in two-second microphone hardware test for VENTUNO Q.

Default invocation INSPECTS ONLY tool availability. Actual audio capture
requires two explicit flags. Captures only to a bounded in-memory buffer,
reports aggregate sample/volume metrics, discards PCM immediately, and
never records to files, streams over the network, or starts STT/GenieX.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.ventuno_alsa_capture_inventory import proc_pcm_inventory

SAMPLE_RATE = 16000
SECONDS = 2
BYTES_EXPECTED = SAMPLE_RATE * SECONDS * 2
MAX_OUTPUT_BYTES = 96_000
TIMEOUT_SECONDS = 6

def classify_alsa_error(stderr: bytes | None) -> str:
    """Classify arecord failures without ever returning raw stderr.

    Categories are diagnostic hints, not proven root causes. Never include
    user audio, device names, or command output in reports/CI logs.
    """
    if not isinstance(stderr, (bytes, bytearray)):
        return "unclassified"
    description = bytes(stderr[:8192]).decode("utf-8", errors="replace").casefold()
    categories = (
        ("access-denied", ("permission denied", "operation not permitted")),
        ("device-busy", ("device or resource busy", "resource busy")),
        ("pcm-not-found", ("unknown pcm", "cannot find card", "no such device",
                           "no such file or directory")),
        ("unsupported-parameters", ("invalid argument", "sample format non available",
                                     "channels count non available",
                                     "unable to set hw params", "rate not available")),
        ("io-failure", ("input/output error", "i/o error", "broken pipe")),
    )
    for category, phrases in categories:
        if any(phrase in description for phrase in phrases):
            return category
    return "unclassified"



def evaluate_pcm(raw: bytes) -> dict[str, object]:
    if len(raw) != BYTES_EXPECTED:
        return {
            "status": "inconclusive-unexpected-raw-length",
            "bytes_received": len(raw),
            "captured_sound_present": False,
        }
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    sum_sq = sum(int(x) * int(x) for x in samples)
    rms = math.sqrt(sum_sq / len(samples)) / 32768
    peak = max(abs(int(x)) for x in samples) / 32768
    return {
        "status": "microphone-signal-measured" if rms > 0.001
                  else "capture-completed-but-signal-too-low",
        "bytes_received": len(raw),
        "samples": len(samples),
        "sample_rate_hz": SAMPLE_RATE,
        "rms_fraction_of_full_scale": round(rms, 6),
        "peak_fraction_of_full_scale": round(peak, 6),
        "captured_sound_present": rms > 0.001,
        "content_discarded": True,
        "stt_model_loaded": False,
        "geniex_service_touched": False,
    }


def microphone_capture(*, explicit_flag: bool, consent: bool,
                       arm_only: bool = True, device: str | None = None,
                       proc_pcm_path: Path = Path("/proc/asound/pcm")) -> dict[str, object]:
    tool = shutil.which("arecord")
    result: dict[str, object] = {
        "status": "read-only-capture-not-authorized",
        "arecord_available": bool(tool),
        "capture_executed": False,
        "audio_saved_to_disk": False,
        "service_changed": False,
    }
    if not explicit_flag or not consent:
        return result
    if arm_only and platform.machine().lower() not in ("aarch64", "arm64"):
        result["status"] = "reject-non-ventuno-architecture"
        return result
    if not tool:
        result["status"] = "no-go-alsa-utils-arecord-not-installed"
        return result
    # An explicit nondefault device is permitted only for the single
    # hardware capture pair actually seen on VENTUNO Q. This metadata
    # gate never opens a stream and cannot bypass explicit consent.
    if device is not None:
        if device != "plughw:0,1":
            result["status"] = "reject-unapproved-capture-target"
            return result
        pcm = proc_pcm_inventory(proc_pcm_path)
        if (not pcm["proc_pcm_readable"] or
                [0, 1] not in pcm["capture_pcm_hardware_pairs"]):
            result["status"] = "no-go-explicit-capture-device-not-present"
            return result
    # ALSA raw PCM to STDOUT only. Do not log audio samples or file paths.
    argv = [
        tool, "--quiet", "--format=S16_LE",
        "--rate=16000", "--channels=1", "--duration=2",
        "--type=raw", "-",
    ]
    if device is not None:
        argv[1:1] = ["--device=" + device]
    try:
        proc = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=TIMEOUT_SECONDS, check=False,
        )
    except subprocess.TimeoutExpired:
        result["status"] = "capture-timeout"
        return result
    except OSError:
        result["status"] = "capture-launch-error"
        return result
    result["capture_executed"] = True
    if proc.returncode != 0:
        result["status"] = "alsa-capture-nonzero"
        result["alsa_error_category"] = classify_alsa_error(proc.stderr)
        return result
    if len(proc.stdout) > MAX_OUTPUT_BYTES:
        result["status"] = "capture-exceeded-bounded-sample-budget"
        return result
    result.update(evaluate_pcm(proc.stdout))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record-2s", action="store_true",
                        help="Record a two-second in-memory microphone diagnostic")
    parser.add_argument("--consent-to-record", action="store_true",
                        help="Confirm permission to record microphone for two seconds")
    parser.add_argument("--device", choices=("plughw:0,1",),
                        default=None,
                        help="Explicit VENTUNO card 0 capture device 1, NOT automatic")
    args = parser.parse_args()
    report = microphone_capture(
        explicit_flag=args.record_2s, consent=args.consent_to_record,
        device=args.device,
    )
    print("MyAI microphone smoke test:", json.dumps(report, sort_keys=True))
    print("No audio waveform or spoken content is saved or displayed.")
    return 0 if (
        not args.record_2s and not args.consent_to_record
        or report["status"] == "microphone-signal-measured"
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
