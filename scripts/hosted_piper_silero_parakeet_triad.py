"""Three fixed Swedish phrases × three synthesis rates on hosted ARM64.

The voice is a separately checksum-verified Swedish Piper Alma model.
The Parakeet and Silero files are SHA-pinned by the invoking workflow.
Audio and transcripts remain process-local, with only bounded flags
and durations included in the report. Never opens a physical device.
"""
from __future__ import annotations

import argparse
import io
import json
import re
import resource
import time
from pathlib import Path

from modules.voice.piper_alma_provider import PiperAlmaTTS
from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT
from scripts.hosted_parakeet_swedish_fixture import (
    public_pcm_vad_segments, public_ogg_to_pcm, verified_silero_model,
)

RATES = (150, 180, 210)
PHRASES = (
    "Vad heter du?",
    "Hur mycket minne använder datorn?",
    "Vad är temperaturen?",
)
MAX_WAV_BYTES = 1_000_000
MAX_CAPTURE_BYTES = 30 * 16_000 * 2


def _wav_to_16k_pcm(wav: bytes) -> bytes:
    import av
    if not 44 <= len(wav) <= MAX_WAV_BYTES:
        raise ValueError("Invalid synthetic Piper WAV")
    collected = bytearray()
    try:
        with av.open(io.BytesIO(wav), mode="r", format="wav") as container:
            if len(container.streams.audio) != 1:
                raise ValueError("Expected mono synthetic audio")
            resampler = av.AudioResampler(format="s16", layout="mono", rate=16000)
            for frame in container.decode(container.streams.audio[0]):
                for output in resampler.resample(frame):
                    collected.extend(output.to_ndarray().tobytes())
                    if len(collected) > MAX_CAPTURE_BYTES:
                        raise ValueError("Synthetic audio too long")
            for output in resampler.resample(None):
                collected.extend(output.to_ndarray().tobytes())
    except Exception:
        raise RuntimeError("Synthetic speech resampling failed") from None
    if not 3200 <= len(collected) <= MAX_CAPTURE_BYTES or len(collected) % 2:
        raise ValueError("Synthetic speech PCM invalid")
    return bytes(collected)


def _normalize(text):
    return " ".join(re.findall(r"[a-zåäö]+", text.casefold()))


def _distance_band(expected, observed):
    """Bounded, source-independent quality metric; never leak decoded text."""
    left, right = _normalize(expected), _normalize(observed)
    if len(right) > 220 or len(left) > 220:
        return "invalid"
    prev = list(range(len(right) + 1))
    for i, a in enumerate(left, 1):
        now = [i]
        for j, b in enumerate(right, 1):
            now.append(min(now[-1] + 1, prev[j] + 1, prev[j - 1] + (a != b)))
        prev = now
    score = prev[-1]
    if score == 0:
        return "0"
    if score <= 2:
        return "1-2"
    if score <= 5:
        return "3-5"
    if score <= 10:
        return "6-10"
    return "11+"


def benchmark(parakeet: Path, silero: Path, alma: Path) -> dict:
    if not verified_silero_model(silero):
        raise RuntimeError("Silero checksum rejected")
    piper = PiperAlmaTTS(voice_id=str(alma), rate=180)
    piper._verified_voice_path()
    recognizer = SherpaOnnxParakeetSTT(model_name=str(parakeet))
    now = time.monotonic()
    recognizer._load_model()
    stt_loaded = round(time.monotonic() - now, 3)
    outcomes = []
    try:
        for rate in RATES:
            piper.rate = rate
            for phrase_id, phrase in enumerate(PHRASES):
                start = time.monotonic()
                synthetic = piper.render_wav(phrase)
                pcm = _wav_to_16k_pcm(synthetic)
                # 400 ms pre-roll / 600 ms tail emulate turn-taking
                # without user microphones or production audio.
                captured = bytes(12800) + pcm + bytes(19200)
                segments = public_pcm_vad_segments(captured, silero)
                whole = recognizer.transcribe(captured)["text"]
                segment_text = (
                    recognizer.transcribe(segments[0])["text"] if segments else ""
                )
                outcomes.append({
                    "phrase_case": phrase_id + 1,
                    "rate": rate,
                    "whole_exact": _normalize(whole) == _normalize(phrase),
                    "silero_exact": _normalize(segment_text) == _normalize(phrase),
                    "whole_distance_band": _distance_band(phrase, whole),
                    "silero_distance_band": _distance_band(phrase, segment_text),
                    "silero_segments": len(segments),
                    "synthetic_seconds": round(len(captured) / 32000, 3),
                    "elapsed_seconds": round(time.monotonic() - start, 3),
                })
    finally:
        recognizer.release_for_inference()
        piper.release_for_inference()

    baseline = [row for row in outcomes if row["rate"] == 180]
    baseline_count = sum(row["silero_exact"] for row in baseline)
    return {
        "status": "hosted-piper-silero-parakeet-rate-matrix-complete",
        "phrase_count": len(PHRASES),
        "rate_count": len(RATES),
        "scenario_count": len(outcomes),
        "baseline_180_silero_exact_count": baseline_count,
        "whole_exact_count": sum(x["whole_exact"] for x in outcomes),
        "silero_exact_count": sum(x["silero_exact"] for x in outcomes),
        "results": outcomes,
        "parakeet_model_load_seconds": stt_loaded,
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "microphone_opened": False, "speaker_opened": False,
        "audio_saved": False, "user_content_used": False,
        "production_services_changed": False,
    }

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parakeet", type=Path, required=True)
    parser.add_argument("--silero", type=Path, required=True)
    parser.add_argument("--alma", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = benchmark(args.parakeet, args.silero, args.alma)
    except Exception as error:
        print(json.dumps({
            "status": "no-go-hosted-speech-triad",
            "exception_class": type(error).__name__,
            "microphone_opened": False, "speaker_opened": False,
        }))
        return 2
    print(json.dumps(report, sort_keys=True))
    return 0 if report["baseline_180_silero_exact_count"] >= 2 else 3


if __name__ == "__main__":
    raise SystemExit(main())
