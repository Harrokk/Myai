"""Hosted/off-device synthetic Swedish Whisper timing/gain sensitivity study.

Only generated Piper Alma "Vad heter du?" reaches SHA256-pinned Whisper
Tiny. No microphone/speaker, user recording, LLM, private transcript, or
permanent MyAI setting is used. Never broadens live voice allowlists.

Compared with the pre-existing pinned Piper 8/8 and eSpeak 0/8 benchmarks,
this probes capture placement and attenuation, not actual user's lost audio.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import os
from pathlib import Path
import platform
import sys

from scripts.ventuno_piper_alma_swedish_stt import (
    _download_verified_voice, _render_once, VOICE_MODEL,
)
from scripts.ventuno_whisper_base_swedish_comparison import (
    _INFERENCE, _limited_child, STT_PYTHON, SMALL_FOLDER,
    EXPECTED_MODEL_SHA256, model_integrity,
)
from scripts.ventuno_synthetic_swedish_question_stt import (
    CAPTURE_BYTES, wav_to_three_second_capture,
)
from scripts.ventuno_usb_dialogue_once import (
    classify_pcm_quality, classify_pcm_activity_layout,
)
from scripts.ventuno_voice_wheel_staging import (
    mem_available_kib, disk_free_bytes,
)
from scripts.ventuno_whisper_tiny_cpu_smoke import (
    MIN_MEM_AVAILABLE_KIB, MIN_DISK_AVAILABLE_BYTES,
)

FIXTURE_VARIANTS = (
    "reference", "early_250ms", "late_400ms", "gain_25pct",
    "noise_snr_12db", "noise_snr_0db", "echo_180ms", "onset_muted_700ms",
)
APPROVED_CATEGORIES = ("approved", "empty", "short-unmatched", "other-unmatched")
MIN_FREE_DISK = max(MIN_DISK_AVAILABLE_BYTES, 4 * 1024**3)


def perturb_three_second_pcm(raw: bytes, *, shift_ms: int = 0,
                             gain_pct: int = 100) -> bytes:
    """Deterministic zero-filled shift; no interpolation or speech text."""
    if (type(raw) is not bytes or len(raw) != CAPTURE_BYTES
            or type(shift_ms) is not int or not -250 <= shift_ms <= 400
            or type(gain_pct) is not int or gain_pct not in (25, 100)):
        raise ValueError("Invalid bounded synthetic fixture or perturbation")
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    expected = CAPTURE_BYTES // 2
    if len(samples) != expected:
        raise ValueError("Invalid 16-bit PCM frame count")
    count = shift_ms * 16
    result = array.array("h", [0]) * expected
    start = max(0, count)
    for dst in range(start, min(expected, expected + count)):
        src = dst - count
        value = int(samples[src]) * gain_pct
        scaled = max(-32768, min(32767, round(value / 100)))
        result[dst] = scaled
    if sys.byteorder != "little":
        result.byteswap()
    wire = result.tobytes()
    if len(wire) != CAPTURE_BYTES:
        raise ValueError("Unexpected private PCM size")
    return wire


def apply_fixed_acoustic_fault(raw: bytes, *, fault: str) -> bytes:
    """Deterministic offline-only noise/echo/cutout; never real audio.

    Noise uses a fixed-seed arithmetic sequence, not a microphone noise
    recording. SNR is relative to the synthetic voice RMS across 3 seconds.
    The results do NOT model an actual VENTUNO acoustical transfer function.
    """
    if type(raw) is not bytes or len(raw) != CAPTURE_BYTES or fault not in (
        "noise_snr_12db", "noise_snr_0db", "echo_180ms",
        "onset_muted_700ms",
    ):
        raise ValueError("Unknown bounded synthetic acoustic fixture")
    original = array.array("h")
    original.frombytes(raw)
    if sys.byteorder != "little":
        original.byteswap()
    if len(original) != CAPTURE_BYTES // 2:
        raise ValueError("Invalid PCM sample count")
    if fault == "onset_muted_700ms":
        original[:11200] = array.array("h", [0]) * 11200
    elif fault == "echo_180ms":
        offset = 180 * 16
        for i in range(len(original) - 1, offset - 1, -1):
            level = int(original[i]) + round(int(original[i - offset]) * 0.35)
            original[i] = max(-32768, min(32767, level))
    else:
        voice_rms = math.sqrt(sum(int(x)**2 for x in original) / len(original))
        snr_db = 12 if fault == "noise_snr_12db" else 0
        target_noise_rms = voice_rms / (10 ** (snr_db / 20))
        # Uniform synthetic noise with mean ~0 and standard deviation ~1.
        # LCG seed is intentionally fixed for repeatable *offline* tests.
        state = 0x13579BDF
        noise_gain = target_noise_rms * math.sqrt(3)
        for i in range(len(original)):
            state = (1664525 * state + 1013904223) & 0xFFFFFFFF
            noise = ((state / 0xFFFFFFFF) * 2.0 - 1.0) * noise_gain
            value = round(int(original[i]) + noise)
            original[i] = max(-32768, min(32767, value))
    if sys.byteorder != "little":
        original.byteswap()
    result = original.tobytes()
    if len(result) != CAPTURE_BYTES:
        raise ValueError("Unexpected bounded synthetic audio length")
    return result


def build_variants(piper_pcm: bytes) -> tuple[bytes, ...]:
    return (
        perturb_three_second_pcm(piper_pcm),
        perturb_three_second_pcm(piper_pcm, shift_ms=-250),
        perturb_three_second_pcm(piper_pcm, shift_ms=400),
        perturb_three_second_pcm(piper_pcm, gain_pct=25),
        apply_fixed_acoustic_fault(piper_pcm, fault="noise_snr_12db"),
        apply_fixed_acoustic_fault(piper_pcm, fault="noise_snr_0db"),
        apply_fixed_acoustic_fault(piper_pcm, fault="echo_180ms"),
        apply_fixed_acoustic_fault(piper_pcm, fault="onset_muted_700ms"),
    )


def inspect_synthetic_window_robustness(
    root: Path, *, authorized: bool = False,
    machine: str | None = None,
) -> dict[str, object]:
    report: dict[str, object] = {
        "status": "not-authorized",
        "tiny_shas_verified": False,
        "piper_model_verified": False,
        "variants_run": 0, "results": [],
        "microphone_opened": False, "speaker_opened": False,
        "user_audio_used": False, "waveform_saved": False,
        "transcript_logged": False, "ollama_called": False,
        "geniex_called": False, "production_modified": False,
        "real_human_speech_robustness_proven": False,
    }
    if not authorized:
        return report
    if (machine or platform.machine()).lower() not in ("arm64", "aarch64"):
        report["status"] = "reject-non-arm64"
        return report
    base = os.environ.get("RUNNER_TEMP", "")
    try:
        if (not base or root.is_symlink()
                or root.resolve(strict=True).parent !=
                Path(base).resolve(strict=True)
                or not root.name.startswith("myai-stt-window-")):
            report["status"] = "reject-unsafe-test-root"
            return report
    except (ValueError, OSError):
        report["status"] = "reject-unsafe-test-root"
        return report
    if ((mem_available_kib() or 0) < MIN_MEM_AVAILABLE_KIB or
            (disk_free_bytes(root) or 0) < MIN_FREE_DISK):
        report["status"] = "reject-insufficient-resources"
        return report
    tiny = root / SMALL_FOLDER
    stt_py = root / STT_PYTHON
    if (not stt_py.is_file() or tiny.is_symlink()
            or model_integrity(tiny).get("model_sha256") !=
            EXPECTED_MODEL_SHA256):
        report["status"] = "reject-unpinned-whisper-tiny"
        return report
    report["tiny_shas_verified"] = True
    piper_dir = root / "pinned-piper-alma"
    if not _download_verified_voice(piper_dir):
        report["status"] = "reject-piper-model-integrity"
        return report
    report["piper_model_verified"] = True
    speech_wav = _render_once(root, piper_dir / VOICE_MODEL, 1.0)
    if speech_wav is None:
        report["status"] = "reject-synthetic-voice-render"
        return report
    raw = wav_to_three_second_capture(speech_wav)
    del speech_wav
    if raw is None:
        report["status"] = "reject-invalid-synthetic-pcm"
        return report
    variants = build_variants(raw)
    del raw
    for start in range(0, len(variants), 2):
        pair = variants[start] + variants[start+1]
        for v in variants[start:start+2]:
            if classify_pcm_quality(v) in (
                "invalid-pcm", "silence-or-too-quiet",
                "possible-microphone-clipping",
            ):
                report["status"] = "reject-invalid-synthetic-energy"
                return report
        child = _limited_child(stt_py, _INFERENCE, root,
                               model=tiny, pcm=pair)
        del pair
        if not child.get("ok"):
            report["status"] = "tiny-window-inference-unavailable"
            return report
        response = child.get("payload")
        if (type(response) is not dict
                or response.get("local_cpu_model_loaded") is not True
                or response.get("mic_used") is not False
                or response.get("speaker_used") is not False):
            report["status"] = "invalid-synthetic-decoder-result"
            return report
        results = response.get("measurements")
        if type(results) is not list or len(results) != 4:
            report["status"] = "invalid-synthetic-measurement-count"
            return report
        for n, item in enumerate(results):
            expected_beam = (1, 5)[n % 2]
            prox = item.get("proximity") if type(item) is dict else None
            if (type(item) is not dict
                    or item.get("beam") != expected_beam
                    or type(item.get("matched")) is not bool
                    or item.get("category") not in APPROVED_CATEGORIES
                    or type(prox) is not dict
                    or prox.get("distance_band")
                        not in ("0", "1-2", "3-5", "6-10", "11+")
                    or type(prox.get("target_words_present")) is not int
                    or not 0 <= prox["target_words_present"] <= 3
                    or type(item.get("seconds")) not in (int, float)
                    or not 0 <= item["seconds"] <= 175):
                report["status"] = "invalid-synthetic-decoder-result"
                return report
            position = start + n // 2
            report["results"].append({
                "variant": FIXTURE_VARIANTS[position],
                "beam": expected_beam,
                "exact_match": item["matched"],
                "word_overlap": prox["target_words_present"],
                "edit_distance_band": prox["distance_band"],
                "seconds": round(item["seconds"], 2),
                "activity_layout": classify_pcm_activity_layout(
                    variants[position]),
            })
        report["variants_run"] += 2
    del variants
    report["status"] = "offline-synthetic-window-inference-completed"
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runner-temp", type=Path, required=True)
    parser.add_argument("--allow-offline-synthetic-only", action="store_true")
    args = parser.parse_args()
    result = inspect_synthetic_window_robustness(
        args.runner_temp, authorized=args.allow_offline_synthetic_only,
    )
    print("Private synthetic Whisper capture-placement results:",
          json.dumps(result, sort_keys=True))
    return 0 if result["status"] in (
        "not-authorized", "offline-synthetic-window-inference-completed",
    ) else 2


if __name__ == "__main__":
    raise SystemExit(main())
