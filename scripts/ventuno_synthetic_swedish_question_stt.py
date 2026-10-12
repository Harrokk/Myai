"""Diagnose Swedish question recognition with synthetic PCM, no audio devices.

Reuse the pinned CPU Whisper model from the proven reference-word test,
then run its *actual live microphone* 16 kHz mono S16_LE inference adapter
against two short eSpeak Swedish utterances, prepared only in memory.

This does not capture user speech, use a microphone or speaker, call
GenieX/Ollama, log transcripts, or change running services.
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
import subprocess
import sys
import wave

from scripts.ventuno_usb_dialogue_hardware import (
    _limited_whisper_child, STT_PYTHON, MODEL_FOLDER, TTS_FOLDER,
)
from scripts.ventuno_usb_dialogue_once import (
    CAPTURE_BYTES, approved_short_question, classify_unapproved_question,
    classify_pcm_quality,
)
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MIN_MEM_AVAILABLE_KIB, model_integrity,
)
from scripts.ventuno_tts_temp_stage import espeak_paths
from scripts.ventuno_voice_wheel_staging import mem_available_kib

PHRASE = "Vad heter du?"
TARGET_RATE = 16000
TARGET_SAMPLES = CAPTURE_BYTES // 2
LEADING_SAMPLES = 5600  # 350 ms before the synthetic speech starts.
SOURCE_MAX_BYTES = 600_000
SPEEDS = (175, 130)


def wav_to_three_second_capture(wav_bytes: bytes) -> bytes | None:
    """Read bounded mono PCM WAV, resample, pad to exactly 3s of capture."""
    if not isinstance(wav_bytes, bytes) or not 44 <= len(wav_bytes) <= SOURCE_MAX_BYTES:
        return None
    try:
        with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
            if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                    or wav.getcomptype() != "NONE"
                    or not 8000 <= wav.getframerate() <= 48000):
                return None
            rate = wav.getframerate()
            # A streamed WAV may report a sentinel frame count; cap read
            # using actual data, never trust the header's frame count.
            raw = wav.readframes(int(rate * 2.60) + 2)
    except (OSError, EOFError, ValueError, wave.Error):
        return None
    if len(raw) % 2 or len(raw) < 200 or len(raw) > 2 * (int(rate * 2.60) + 2):
        return None
    original = array.array("h")
    original.frombytes(raw)
    if sys.byteorder != "little":
        original.byteswap()
    if len(original) / rate > 2.55:
        return None
    length = round(len(original) * TARGET_RATE / rate)
    if not 1500 <= length <= TARGET_SAMPLES - LEADING_SAMPLES:
        return None

    output = array.array("h", [0]) * TARGET_SAMPLES
    # Bounded linear interpolation is enough to test short eSpeak speech
    # without depending on host audio libraries or microphone timing.
    for pos in range(length):
        source = pos * rate / TARGET_RATE
        a = min(int(source), len(original) - 1)
        b = min(a + 1, len(original) - 1)
        fraction = source - a
        output[LEADING_SAMPLES + pos] = round(
            int(original[a]) * (1 - fraction) + int(original[b]) * fraction
        )
    if sys.byteorder != "little":
        output.byteswap()
    data = output.tobytes()
    return data if len(data) == CAPTURE_BYTES else None


def analyze_isolated_synthetic_question(
    root: Path, *, authorized: bool = False, machine: str | None = None,
) -> dict[str, object]:
    """Only private synthetic audio reaches pinned offline Whisper CPU."""
    report: dict[str, object] = {
        "status": "not-authorized",
        "synthetic_variants_run": 0,
        "normal_speed_question_matched": False,
        "slow_speed_question_matched": False,
        "normal_speed_category": "not-run",
        "slow_speed_category": "not-run",
        "real_microphone_opened": False,
        "real_speaker_opened": False,
        "user_audio_processed": False,
        "transcript_logged": False,
        "waveform_saved": False,
        "geniex_called": False,
        "ollama_called": False,
        "production_settings_changed": False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("aarch64", "arm64"):
        report["status"] = "blocked-architecture"
        return report
    temp = os.environ.get("RUNNER_TEMP", "")
    try:
        if (not temp or root.is_symlink() or
                not root.resolve(strict=True).is_relative_to(
                    Path(temp).resolve(strict=True)
                ) or
                not root.name.startswith("myai-synthetic-phrase-")):
            report["status"] = "blocked-nonisolated-workspace"
            return report
    except OSError:
        report["status"] = "blocked-nonisolated-workspace"
        return report
    if (mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB:
        report["status"] = "blocked-memory-reserve"
        return report

    model_dir = root / MODEL_FOLDER
    python_bin = root / STT_PYTHON
    voice_dir = root / TTS_FOLDER
    if (not python_bin.is_file() or model_dir.is_symlink()
            or model_integrity(model_dir).get("model_metadata_complete") is not True):
        report["status"] = "blocked-unverified-model"
        return report
    executable, voice_data = espeak_paths(voice_dir)
    if executable is None or voice_data is None:
        report["status"] = "blocked-unverified-tts"
        return report
    env = os.environ.copy()
    env["LD_LIBRARY_PATH"] = (
        str(voice_dir / "extracted/usr/lib/aarch64-linux-gnu")
        + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    )

    for i, speed in enumerate(SPEEDS):
        try:
            synth = subprocess.run(
                [str(executable), "--path=" + str(voice_data.parent),
                 "-v", "sv", "-s", str(speed), "--stdout", PHRASE],
                cwd=voice_dir, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, check=False, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            report["status"] = "synthetic-swedish-tts-failed"
            return report
        if synth.returncode:
            report["status"] = "synthetic-swedish-tts-failed"
            return report
        pcm = wav_to_three_second_capture(synth.stdout)
        del synth
        if pcm is None:
            report["status"] = "synthetic-capture-format-rejected"
            return report
        category = classify_pcm_quality(pcm)
        if category in ("invalid-pcm", "silence-or-too-quiet",
                        "possible-microphone-clipping"):
            report["status"] = "synthetic-audio-level-rejected"
            return report
        try:
            decoded = _limited_whisper_child(root, python_bin, model_dir, pcm)
        except (OSError, RuntimeError, ValueError, TimeoutError, TypeError):
            report["status"] = "offline-whisper-synthetic-inference-failed"
            return report
        del pcm
        expected = approved_short_question(decoded) == "vad heter du"
        # Output categories only: no raw decoded words, audio, or results.
        label = "normal" if i == 0 else "slow"
        report[label + "_speed_question_matched"] = expected
        report[label + "_speed_category"] = (
            "approved" if expected else classify_unapproved_question(decoded)
        )
        report["synthetic_variants_run"] += 1
        del decoded
    report["status"] = "synthetic-swedish-phrase-inference-completed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--isolated-synthetic-speech-only", action="store_true")
    args = parser.parse_args()
    result = analyze_isolated_synthetic_question(
        args.runner_temp,
        authorized=args.isolated_synthetic_speech_only,
    )
    print("VENTUNO offline synthetic Swedish question recognition:",
          json.dumps(result, sort_keys=True))
    # A completed mismatch is a useful diagnostic, not a system failure.
    return 0 if result["status"] in (
        "not-authorized", "synthetic-swedish-phrase-inference-completed",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
