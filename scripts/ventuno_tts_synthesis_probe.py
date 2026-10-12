"""Safe Swedish synthetic TTS preflight for Arduino VENTUNO Q.

Default: check for the *presence* of espeak-ng/espeak only.
Explicit --synthesize-synthetic-phrase: synthesize a short, fixed Swedish
phrase to an in-memory WAV buffer WITHOUT opening any audio device.
No microphone, network calls, speech content files, systemd changes,
production Python provider imports, or background processes.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import shutil
import subprocess
import wave

PHRASE = "Hej. Jag heter My AI."
EXECUTABLE_NAMES = ("espeak-ng", "espeak")
MAX_WAV_BYTES = 1_000_000
MAX_DURATION_SECONDS = 6
MIN_DURATION_SECONDS = 0.25
TIMEOUT_SECONDS = 8


def validate_wav(raw: bytes) -> dict[str, object]:
    """Only count a parseable non-silent mono PCM16 WAV as synthetic speech."""
    result = {
        "wav_header_valid": False,
        "wav_pcm16_mono": False,
        "sample_rate_hz": None,
        "duration_seconds": None,
        "rms_fraction_full_scale": None,
        "nonzero_samples": None,
        "signal_verified": False,
    }
    if not isinstance(raw, bytes) or not 44 <= len(raw) <= MAX_WAV_BYTES:
        return result
    if not raw.startswith(b"RIFF") or raw[8:12] != b"WAVE":
        return result
    try:
        with wave.open(io.BytesIO(raw), "rb") as handle:
            channels = handle.getnchannels()
            width = handle.getsampwidth()
            sample_rate = handle.getframerate()
            declared_frames = handle.getnframes()
            compression = handle.getcomptype()
            if (channels != 1 or width != 2 or compression != "NONE"
                    or sample_rate not in (16000, 22050, 24000, 44100, 48000)
                    or declared_frames < 1):
                return result
            # espeak --stdout sends a non-seekable WAV with a sentinel-sized
            # RIFF/data length. Respect actual bounded buffer size, never
            # trust the sentinel as a literal duration.
            pcm = handle.readframes(min(declared_frames, MAX_WAV_BYTES // 2))
            if len(pcm) < 2 or len(pcm) % 2:
                return result
            frames = len(pcm) // 2
            seconds = frames / sample_rate
            if not MIN_DURATION_SECONDS <= seconds <= MAX_DURATION_SECONDS:
                return result
    except (ValueError, EOFError, OSError, wave.Error):
        return result
    import array
    import sys
    samples = array.array("h")
    samples.frombytes(pcm)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(v) for v in samples), default=0)
    mean_sq = sum(int(v) * int(v) for v in samples) / len(samples)
    rms = math.sqrt(mean_sq) / 32768
    result.update({
        "wav_header_valid": True,
        "wav_pcm16_mono": True,
        "sample_rate_hz": sample_rate,
        "duration_seconds": round(seconds, 3),
        "rms_fraction_full_scale": round(rms, 6),
        "nonzero_samples": sum(v != 0 for v in samples),
        "signal_verified": bool(peak > 0 and rms >= 0.001),
    })
    return result


def preferred_tts_tool() -> tuple[str | None, str | None]:
    for name in EXECUTABLE_NAMES:
        candidate = shutil.which(name)
        if candidate:
            return name, candidate
    return None, None


def evaluate_tts(*, synthesize: bool = False) -> dict[str, object]:
    name, tool = preferred_tts_tool()
    result: dict[str, object] = {
        "status": "tts-cli-not-detected",
        "backend": name,
        "synthetic_synthesis_attempted": False,
        "tts_synthetic_signal_verified": False,
        "physical_speaker_playback_verified": False,
        "pyttsx3_provider_verified": False,
        "microphone_opened": False,
        "audio_saved_to_disk": False,
        "network_used": False,
        "production_services_changed": False,
    }
    if not tool:
        return result
    if not synthesize:
        result["status"] = "tts-cli-present-synthesis-not-attempted"
        return result
    result["synthetic_synthesis_attempted"] = True
    try:
        # --stdout synthesizes PCM to a pipe; no ALSA/Pulse/PipeWire playback.
        proc = subprocess.run(
            [tool, "-v", "sv", "--stdout", PHRASE],
            capture_output=True,
            timeout=TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired:
        result["status"] = "tts-cli-timeout"
        return result
    except OSError:
        result["status"] = "tts-cli-launch-error"
        return result
    if proc.returncode != 0:
        result["status"] = "tts-cli-nonzero"
        return result
    wav_result = validate_wav(proc.stdout)
    result.update(wav_result)
    result["tts_synthetic_signal_verified"] = wav_result["signal_verified"]
    result["status"] = (
        "swedish-synthetic-tts-wav-verified"
        if wav_result["signal_verified"]
        else "inconclusive-synthetic-tts-wav"
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--synthesize-synthetic-phrase", action="store_true",
                        help="Fixed Swedish text to in-memory WAV, no playback")
    args = parser.parse_args()
    report = evaluate_tts(synthesize=args.synthesize_synthetic_phrase)
    print("VENTUNO offline Swedish TTS:", json.dumps(report, sort_keys=True))
    print("No loudspeaker or microphone opened; no production changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
