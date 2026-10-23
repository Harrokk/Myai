"""Exercise the EXACT isolated decoder used in one-shot VENTUNO audio, offline.

Uses only SHA256-pinned synthetic Piper Alma speech and Whisper Tiny on a
GitHub-hosted ARM64 runner. Reuses _limited_whisper_child with the production
_PRIVATE_WHISPER, not the separate metrics benchmark decoder. The private
transcript never leaves this function. No microphone, speaker, GenieX, voice
command expansion, persistent WAV, hardware runner or user utterance.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import platform

from scripts.ventuno_piper_alma_swedish_stt import (
    _download_verified_voice, _render_once, VOICE_MODEL,
)
from scripts.ventuno_synthetic_swedish_question_stt import (
    CAPTURE_BYTES, wav_to_three_second_capture,
)
from scripts.ventuno_stt_synthetic_window_robustness import (
    apply_fixed_acoustic_fault,
)
from scripts.ventuno_usb_dialogue_hardware import _limited_whisper_child
from scripts.ventuno_usb_dialogue_once import (
    approved_short_question, classify_unapproved_question,
    classify_pcm_activity_layout, classify_pcm_quality,
)
from scripts.ventuno_whisper_base_swedish_comparison import (
    STT_PYTHON, SMALL_FOLDER, EXPECTED_MODEL_SHA256, model_integrity,
)
from scripts.ventuno_voice_wheel_staging import (
    mem_available_kib, disk_free_bytes,
)
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MIN_MEM_AVAILABLE_KIB, MIN_DISK_AVAILABLE_BYTES,
)

VARIANTS = (
    "clean_piper",
    "middle_window_800ms",
    "noise_12db",
    "noise_0db",
    "first_700ms_muted",
)


def shift_piper_to_middle(raw: bytes) -> bytes:
    """800ms silent prefix with tail truncation, fixed 3s sample count."""
    if type(raw) is not bytes or len(raw) != CAPTURE_BYTES:
        raise ValueError("Expected one bounded synthetic 3s PCM clip")
    shift = 800 * 16 * 2  # milliseconds -> 16kHz, signed 16-bit mono
    return bytes(shift) + raw[:CAPTURE_BYTES - shift]
MIN_FREE_DISK = max(4 * 1024 ** 3, MIN_DISK_AVAILABLE_BYTES)


def private_exact_decoder_trial(
    raw: bytes, *, decode, variant: str,
) -> dict[str, object]:
    """Keep decoded words LOCAL. Export allowlisted non-invertible categories."""
    if (type(raw) is not bytes or len(raw) != CAPTURE_BYTES
            or variant not in VARIANTS):
        raise ValueError("Strict synthetic PCM and fixed fixture label required")
    if classify_pcm_quality(raw) in (
        "invalid-pcm", "silence-or-too-quiet",
        "possible-microphone-clipping",
    ):
        raise ValueError("Invalid synthetic PCM level")
    private_words = decode(raw)
    if type(private_words) is not str or len(private_words) > 96:
        raise ValueError("Invalid private exact-decoder output")
    matched = approved_short_question(private_words) == "vad heter du"
    category = (
        "approved" if matched else classify_unapproved_question(private_words)
    )
    # Do not return, persist, log or hash private_words.
    del private_words
    if category not in (
        "approved", "empty-or-silence", "invalid-or-oversize",
        "unsafe-command-or-control", "spoken-cue-echo-suspected",
        "test-question-with-extra-words", "unrelated-short-utterance",
        "other-unmatched-utterance",
    ):
        raise ValueError("Unrecognized private transcript category")
    return {
        "variant": variant,
        "accepted_exact_harmless_question": matched,
        "private_transcript_category": category,
        "coarse_capture_activity_layout": classify_pcm_activity_layout(raw),
    }


def inspect_exact_live_decoder(
    root: Path, *, synthetic_authorized: bool = False,
    machine: str | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "not-authorized", "model_sha256_verified": False,
        "synthetic_voice_sha256_verified": False, "results": [],
        "microphone_opened": False, "speaker_opened": False,
        "user_audio_used": False, "raw_pcm_or_transcript_saved": False,
        "geniex_called": False, "production_modified": False,
        "real_user_speech_verified": False,
        "authorizes_physical_recording": False,
        "authorizes_physical_playback": False,
    }
    if not synthetic_authorized:
        return report
    if (machine or platform.machine()).lower() not in ("aarch64", "arm64"):
        report["status"] = "reject-non-arm64"
        return report
    temp = os.environ.get("RUNNER_TEMP", "")
    try:
        if (not temp or root.is_symlink()
                or root.resolve(strict=True).parent !=
                Path(temp).resolve(strict=True)
                or not root.name.startswith("myai-stt-window-")):
            report["status"] = "reject-unsafe-workspace"
            return report
    except (ValueError, OSError):
        report["status"] = "reject-unsafe-workspace"
        return report
    if ((mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB or
            (disk_free_bytes(root) or 0) < MIN_FREE_DISK):
        report["status"] = "reject-insufficient-resources"
        return report
    py = root / STT_PYTHON
    tiny = root / SMALL_FOLDER
    if (not py.is_file() or tiny.is_symlink()
            or model_integrity(tiny).get("model_sha256")
                != EXPECTED_MODEL_SHA256):
        report["status"] = "reject-unpinned-tiny-model"
        return report
    report["model_sha256_verified"] = True
    voice_dir = root / "pinned-piper-alma"
    if not _download_verified_voice(voice_dir):
        report["status"] = "reject-unpinned-piper-voice"
        return report
    report["synthetic_voice_sha256_verified"] = True
    wav = _render_once(root, voice_dir / VOICE_MODEL, 1.0)
    if wav is None:
        report["status"] = "reject-synthetic-render"
        return report
    raw = wav_to_three_second_capture(wav)
    del wav
    if raw is None or len(raw) != CAPTURE_BYTES:
        report["status"] = "reject-synthetic-pcm-format"
        return report
    cases = (
        ("clean_piper", raw),
        ("middle_window_800ms", shift_piper_to_middle(raw)),
        ("noise_12db", apply_fixed_acoustic_fault(
            raw, fault="noise_snr_12db")),
        ("noise_0db", apply_fixed_acoustic_fault(
            raw, fault="noise_snr_0db")),
        ("first_700ms_muted", apply_fixed_acoustic_fault(
            raw, fault="onset_muted_700ms")),
    )
    del raw
    for label, pcm in cases:
        try:
            item = private_exact_decoder_trial(
                pcm, variant=label,
                decode=lambda v: _limited_whisper_child(root, py, tiny, v),
            )
        except (ValueError, RuntimeError, OSError):
            report["status"] = "exact-decoder-unavailable-or-invalid"
            return report
        report["results"].append(item)
    report["status"] = "synthetic-exact-production-decoder-completed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--allow-offline-synthetic-only", action="store_true")
    args = parser.parse_args()
    result = inspect_exact_live_decoder(
        args.runner_temp,
        synthetic_authorized=args.allow_offline_synthetic_only,
    )
    print("Exact production STT on synthetic-only Piper:",
          json.dumps(result, sort_keys=True))
    return 0 if result["status"] in (
        "not-authorized",
        "synthetic-exact-production-decoder-completed",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
