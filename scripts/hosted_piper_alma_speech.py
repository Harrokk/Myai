"""Native Piper Alma public-text synthesis benchmark on disposable ARM64 only.

Renders fixed, non-user Swedish text directly into memory. A voice checksum
and metadata check precede model loading. No microphone, output device, WAV
file, GenieX request or user content is involved.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import resource
import time
import wave
from pathlib import Path

from modules.voice.piper_alma_provider import PiperAlmaTTS

VOICE_SHA256 = "f75455eb6afeb1db9e2905d5bd7e4115afcd3710e0d399b6a40981766d32fedc"
VOICE_NAME = "sv_SE-alma-medium.onnx"
FIXED_TEXT = "Hej. Jag heter MyAI."


def benchmark(voice: Path) -> dict:
    if (not voice.is_absolute() or voice.is_symlink()
            or not voice.is_file() or voice.name != VOICE_NAME):
        raise RuntimeError("Pinned Alma model not present")
    # Delegate pinned SHA-256 and metadata checks to the actual product provider.
    provider = PiperAlmaTTS(rate=180, volume=1.0, voice_id=str(voice))
    provider._verified_voice_path()
    begin = time.monotonic()
    wav_data = provider.render_wav(FIXED_TEXT)
    elapsed = time.monotonic() - begin
    with wave.open(io.BytesIO(wav_data), "rb") as wav:
        if (wav.getnchannels() != 1 or wav.getsampwidth() != 2
                or wav.getframerate() != 22050):
            raise ValueError("Invalid native Piper WAV")
        pcm = wav.readframes(wav.getnframes())
        duration = len(pcm) / (22050 * 2)
        if not 0.2 <= duration <= 20:
            raise ValueError("Piper duration invalid")
        import numpy as np
        samples = np.frombuffer(pcm, dtype="<i2")
        if not np.any(samples):
            raise ValueError("Piper audio silent")
        # Never send the raw WAV or synthesized words to CI logs.
    provider.release_for_inference()
    return {
        "status": "pinned-swedish-piper-inmemory-verified",
        "voice_sha256_verified": True,
        "render_seconds": round(elapsed, 3),
        "duration_seconds": round(duration, 3),
        "peak_rss_mib": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1),
        "microphone_used": False,
        "speaker_opened": False,
        "wav_saved": False,
        "user_audio_used": False,
        "geniex_used": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = benchmark(args.model)
    except Exception as error:
        print(json.dumps({
            "status": "no-go-piper-hosted-synthesis",
            "error_type": type(error).__name__,
            "speaker_opened": False,
            "user_audio_used": False,
        }))
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
