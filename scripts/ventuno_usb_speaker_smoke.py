"""Explicitly authorized, single, low-level Swedish USB speaker smoke test.

Renders only a fixed test phrase with staged eSpeak NG into RAM, attenuates
mono 16-bit PCM to a hard digital peak ceiling and sends exactly one bounded
WAV to ALSA USB playback. No microphone, LLM, file audio, package installs,
mixer writes, or production settings modifications.
"""
from __future__ import annotations

import argparse
import array
import io
import json
import math
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import wave

from scripts.ventuno_tts_synthesis_probe import PHRASE
from scripts.ventuno_tts_temp_stage import espeak_paths
from scripts.ventuno_usb_audio_inventory import inventory_usb_audio

DEVICE = "plughw:1,0"
PAIR = [1, 0]
DIGITAL_PEAK_LIMIT = 0.04  # Approx. -28 dBFS, not a physical SPL guarantee.
MAX_WAV_BYTES = 700_000
MAX_DURATION_SECONDS = 3.5
MIN_DURATION_SECONDS = 0.6
MAX_SAMPLE_RATE = 48_000
TIMEOUT_SECONDS = 9


def quiet_wav_from_tts(source: bytes) -> tuple[bytes | None, dict[str, object]]:
    """Reject unexpected WAV and return only bounded, attenuated PCM in a WAV."""
    status: dict[str, object] = {
        "source_wav_valid": False,
        "limited_peak_fraction": None,
        "sample_rate_hz": None,
        "duration_seconds": None,
    }
    if not isinstance(source, bytes) or not 44 <= len(source) <= MAX_WAV_BYTES:
        return None, status
    try:
        with wave.open(io.BytesIO(source), "rb") as stream:
            rate = stream.getframerate()
            if (stream.getnchannels() != 1 or stream.getsampwidth() != 2
                    or stream.getcomptype() != "NONE"
                    or rate not in (16000, 22050, 24000, 44100, 48000)):
                return None, status
            # eSpeak pipes may use sentinel-sized RIFF/data fields. Bound by
            # bytes actually available instead of trusting getnframes().
            pcm = stream.readframes(int(MAX_DURATION_SECONDS * MAX_SAMPLE_RATE) + 1)
    except (OSError, ValueError, EOFError, wave.Error):
        return None, status
    if len(pcm) < 2 or len(pcm) % 2:
        return None, status
    duration = (len(pcm) // 2) / rate
    if not MIN_DURATION_SECONDS <= duration <= MAX_DURATION_SECONDS:
        return None, status
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    source_peak = max(abs(int(s)) for s in samples)
    if source_peak < 32:
        return None, status
    amplitude_limit = int(32767 * DIGITAL_PEAK_LIMIT)
    ratio = min(1.0, amplitude_limit / source_peak)
    quiet = array.array("h", (int(round(int(s) * ratio)) for s in samples))
    limited_peak = max(abs(int(v)) for v in quiet)
    if limited_peak > amplitude_limit:
        return None, status
    if sys.byteorder != "little":
        quiet.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(rate)
        out.writeframes(quiet.tobytes())
    result = output.getvalue()
    if len(result) > MAX_WAV_BYTES:
        return None, status
    status.update({
        "source_wav_valid": True,
        "limited_peak_fraction": round(limited_peak / 32768, 6),
        "sample_rate_hz": rate,
        "duration_seconds": round(duration, 3),
    })
    return result, status


def play_usb_speaker(*, authorized: bool = False,
                     stage_folder: Path,
                     device: str = DEVICE) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "not-authorized",
        "playback_attempted": False,
        "playback_command_succeeded": False,
        "audible_sound_confirmed_by_person": False,
        "mic_recorded": False,
        "speech_transcribed": False,
        "audio_file_saved": False,
        "production_settings_modified": False,
        "services_modified": False,
        "digital_peak_cap": DIGITAL_PEAK_LIMIT,
    }
    if not authorized:
        return report
    if platform.machine().lower() not in ("aarch64", "arm64"):
        report["status"] = "reject-non-arm64"
        return report
    if device != DEVICE:
        report["status"] = "reject-unapproved-device"
        return report
    inventory = inventory_usb_audio()
    nodes = inventory.get("playback_device_nodes", [])
    if (1 not in inventory.get("usb_audio_cards", [])
            or PAIR not in inventory.get("usb_playback_pairs", [])
            or not any(isinstance(n, dict) and n.get("pair") == PAIR
                       and n.get("character_device") is True
                       and n.get("accessible") is True for n in nodes)):
        report["status"] = "usb-speaker-missing-or-renumbered"
        return report
    exe, voice_data = espeak_paths(stage_folder)
    if not exe or not voice_data:
        report["status"] = "isolated-tts-unavailable"
        return report
    aplay = shutil.which("aplay")
    if not aplay:
        report["status"] = "aplay-not-installed"
        return report

    extracted = stage_folder / "extracted"
    environment = os.environ.copy()
    environment["LD_LIBRARY_PATH"] = (
        str(extracted / "usr/lib/aarch64-linux-gnu")
        + os.pathsep + environment.get("LD_LIBRARY_PATH", "")
    )
    try:
        synthesis = subprocess.run(
            [str(exe), "--path=" + str(voice_data.parent),
             "-v", "sv", "--stdout", PHRASE],
            cwd=stage_folder, env=environment, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, check=False, timeout=TIMEOUT_SECONDS,
        )
    except (subprocess.TimeoutExpired, OSError):
        report["status"] = "tts-process-failed"
        return report
    if synthesis.returncode != 0:
        report["status"] = "tts-process-failed"
        return report
    wav_bytes, wave_info = quiet_wav_from_tts(synthesis.stdout)
    report.update(wave_info)
    if not wav_bytes:
        report["status"] = "invalid-or-unbounded-swedish-test-wav"
        return report

    # No file writes; WAV passed to ALSA via stdin exactly once.
    try:
        report["playback_attempted"] = True
        playback = subprocess.run(
            [aplay, "--quiet", "--device=" + DEVICE, "--file-type=wav", "-"],
            input=wav_bytes, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        report["status"] = "speaker-playback-timeout"
        return report
    except OSError:
        report["status"] = "speaker-playback-launch-error"
        return report
    if playback.returncode:
        report["status"] = "alsa-speaker-playback-nonzero"
        return report
    report["playback_command_succeeded"] = True
    report["status"] = "usb-speaker-pcm-playback-completed"
    # A successful aplay exit cannot establish that a human heard the sound.
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--play-fixed-low-level-swedish-phrase", action="store_true")
    parser.add_argument("--consent-to-playback", action="store_true")
    parser.add_argument("--stage-folder", type=Path, required=True)
    parser.add_argument("--device", choices=(DEVICE,), default=DEVICE)
    args = parser.parse_args()
    result = play_usb_speaker(
        authorized=(args.play_fixed_low_level_swedish_phrase
                    and args.consent_to_playback),
        stage_folder=args.stage_folder,
        device=args.device,
    )
    print("VENTUNO USB speaker fixed Swedish test:", json.dumps(result, sort_keys=True))
    return 0 if result["status"] in (
        "not-authorized", "usb-speaker-pcm-playback-completed",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
