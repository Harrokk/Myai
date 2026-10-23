"""Test exactly the production Swedish start cue in-memory on hosted ARM64.

A preflight for the 3.5-second low-peak speaker WAV policy. This module
neither records nor plays sound. It accepts no arbitrary user-supplied speech
text, never persists audio and cannot grant any future physical consent.
"""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import platform
import subprocess

from scripts.ventuno_usb_dialogue_hardware import SPOKEN_START_CUE
from scripts.ventuno_usb_speaker_smoke import (
    MAX_DURATION_SECONDS, MAX_WAV_BYTES, DIGITAL_PEAK_LIMIT,
    quiet_wav_from_tts,
)
from scripts.ventuno_tts_temp_stage import espeak_paths

STATUS = "hosted-swedish-cue-audio-policy-verified"


def evaluate_cue_render(*, root: Path, synthetic_only: bool = False) -> dict:
    report = {
        "status": "not-authorized",
        "exact_live_cue_used": False,
        "audio_duration_seconds": None,
        "digital_peak_cap": DIGITAL_PEAK_LIMIT,
        "max_duration_seconds": MAX_DURATION_SECONDS,
        "physical_microphone_opened": False,
        "physical_speaker_opened": False,
        "llm_called": False,
        "user_audio_used": False,
        "generated_wav_saved": False,
        "production_modified": False,
        "authorizes_physical_recording": False,
        "authorizes_physical_playback": False,
    }
    if not synthetic_only:
        return report
    if platform.machine().lower() not in ("aarch64", "arm64"):
        report["status"] = "reject-non-arm64"
        return report
    temp = os.environ.get("RUNNER_TEMP")
    try:
        if (
            not temp or root.is_symlink() or not root.is_dir()
            or root.name.startswith("myai-cue-render-") is False
            or root.resolve(strict=True).parent != Path(temp).resolve(strict=True)
        ):
            report["status"] = "reject-unsafe-root"
            return report
    except (OSError, ValueError, RuntimeError):
        report["status"] = "reject-unsafe-root"
        return report
    staged = root / "myai-tts-espeak-stage"
    exe, voice = espeak_paths(staged)
    if exe is None or voice is None:
        report["status"] = "reject-unverified-staged-swedish-tts"
        return report
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = (
        str(staged / "extracted/usr/lib/aarch64-linux-gnu")
        + os.pathsep
        + str(staged / "extracted/usr/lib/aarch64-linux-gnu/pulseaudio")
        + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    )
    # Exactly the arguments used in build_ports. Never invoke aplay/arecord.
    command = [
        str(exe), "--path=" + str(voice.parent),
        "-v", "sv", "--stdout", SPOKEN_START_CUE,
    ]
    try:
        proc = subprocess.run(
            command, cwd=staged, env=env, check=False,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=9,
        )
    except (OSError, subprocess.TimeoutExpired):
        report["status"] = "reject-cue-render-unavailable"
        return report
    if proc.returncode or not 44 <= len(proc.stdout) <= MAX_WAV_BYTES:
        # Synthetic-only exit metadata, no stdout/stderr, TTS text or waveform.
        report["status"] = "reject-cue-render-size-or-process"
        report["synthetic_renderer_exit_category"] = (
            "nonzero" if proc.returncode else "zero"
        )
        report["synthetic_wav_size_category"] = (
            "too-short" if len(proc.stdout) < 44 else
            "over-cap" if len(proc.stdout) > MAX_WAV_BYTES else "bounded"
        )
        return report
    safe_wav, info = quiet_wav_from_tts(proc.stdout)
    del proc
    if safe_wav is None:
        report["status"] = "reject-cue-exceeds-quiet-wav-policy"
        return report
    del safe_wav
    if (
        type(info) is not dict
        or type(info.get("duration_seconds")) not in (float, int)
        or not 0 < info["duration_seconds"] <= MAX_DURATION_SECONDS
        or info.get("limited_peak_fraction", 1) > DIGITAL_PEAK_LIMIT
    ):
        report["status"] = "reject-cue-duration-or-peak"
        return report
    report.update({
        "status": STATUS,
        "exact_live_cue_used": True,
        "audio_duration_seconds": info["duration_seconds"],
    })
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scratch", type=Path, required=True)
    parser.add_argument("--synthetic-cue-only", action="store_true")
    args = parser.parse_args()
    report = evaluate_cue_render(
        root=args.scratch, synthetic_only=args.synthetic_cue_only,
    )
    print("Swedish cue safety preflight:", json.dumps(report, sort_keys=True))
    return 0 if report["status"] == STATUS else 2


if __name__ == "__main__":
    raise SystemExit(main())
