# SPDX-License-Identifier: MIT
"""Source-only, operator-run Arduino App Lab RAM-WAV ASR comparison pilot.

A separate experiment from the existing streaming v2 and archived legacy code.
No code records automatically on import: App.run invokes run_one only on Run.
A future physical test REQUIRES separate, explicit operator permission.
This pilot records at most eight seconds of 16-kHz mono signed-16-bit audio
using Arduino's ALSAMicrophone, closes the mic, then transcribes using the
official Arduino WAVAutomaticSpeechRecognition. WAV bytes remain only in RAM.
The application never prints, writes or exports recognized words or PCM.
"""

from __future__ import annotations

import array
import io
import math
import sys
import time
import unicodedata
import wave

from arduino.app_bricks.asr import WAVAutomaticSpeechRecognition
from arduino.app_peripherals.microphone import ALSAMicrophone
from arduino.app_utils import App

MIC_DEVICE = "plughw:1,0"
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_WIDTH = 2
MAX_CAPTURE_SECONDS = 8
MAX_SAMPLES = SAMPLE_RATE * MAX_CAPTURE_SECONDS
MAX_WORD_CHARS = 240
_PREFIX = "MYAI_APP_LAB_WAV_V2: "

# Explicit SDK ALSA device bypasses the ordinal Microphone(0) discovery
# that failed in the earlier App Lab container. Nothing opens until Run.
mic = ALSAMicrophone(
    device=MIC_DEVICE, sample_rate=SAMPLE_RATE,
    channels=CHANNELS, shared=False, auto_reconnect=False,
)
_used = False


def _private_label(raw: object) -> str:
    """Never print raw speech, even if the native engine returns text."""
    if not isinstance(raw, str):
        return "invalid-final-type"
    text = unicodedata.normalize("NFC", raw.strip())
    if not text:
        return "empty-final-only"
    if len(text) > MAX_WORD_CHARS:
        return "invalid-final-too-long"
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in text):
        return "invalid-final-control"
    normalized = " ".join(text.casefold().strip(" .,!?;:").split())
    if normalized == "vad heter du":
        return "reference-recognized"
    return "other-nonempty-final"


def _collect_ram_wav() -> bytes | None:
    """Capture bounded PCM through vendor API; wrap it as WAV only in RAM."""
    parts: list[bytes] = []
    samples = 0
    deadline = time.monotonic() + MAX_CAPTURE_SECONDS
    while samples < MAX_SAMPLES and time.monotonic() < deadline:
        chunk = mic.capture()
        if chunk is None or getattr(chunk, "size", 0) == 0:
            time.sleep(0.01)
            continue
        # Keep at most eight seconds of 16-bit mono PCM, regardless of
        # the size a capture call happens to return.
        n = min(int(chunk.size), MAX_SAMPLES - samples)
        if n <= 0:
            continue
        parts.append(chunk[:n].tobytes())
        samples += n

    if not parts:
        return None

    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(CHANNELS)
        wav.setsampwidth(SAMPLE_WIDTH)
        wav.setframerate(SAMPLE_RATE)
        for part in parts:
            wav.writeframesraw(part)
        wav.writeframes(b"")
    parts.clear()
    return output.getvalue()


def _safe_signal_summary(wav_bytes: bytes) -> str:
    """Report only aggregate levels; never log or retain PCM beyond this call.

    Read the in-RAM WAV with standard library, enforcing the exact expected
    format. No thresholds are used to infer that any speech was recognizable.
    """
    with wave.open(io.BytesIO(wav_bytes), "rb") as wav:
        if (wav.getnchannels() != CHANNELS
                or wav.getsampwidth() != SAMPLE_WIDTH
                or wav.getframerate() != SAMPLE_RATE
                or wav.getnframes() > MAX_SAMPLES):
            raise ValueError("unexpected WAV format")
        pcm_bytes = wav.readframes(MAX_SAMPLES)
    pcm = array.array("h")
    pcm.frombytes(pcm_bytes)
    if sys.byteorder != "little":
        pcm.byteswap()
    if not pcm:
        raise ValueError("WAV has no PCM samples")
    peak = 0
    squared_sum = 0
    saturated = 0
    for sample in pcm:
        absolute = abs(sample)
        if absolute > peak:
            peak = absolute
        squared_sum += sample * sample
        if absolute >= 32760:
            saturated += 1
    rms = math.sqrt(squared_sum / len(pcm))
    return (
        f"signal-level peak-pct={peak * 100 / 32768:.1f}"
        f" rms-pct={rms * 100 / 32768:.1f}"
        f" saturated-samples={saturated}"
    )


def run_one() -> None:
    """One capture, then one offline WAV-ASR call; no repeated recordings."""
    global _used
    if _used:
        raise StopIteration
    _used = True
    status = "no-audio"
    wav_bytes: bytes | None = None
    asr = None
    mic_opened = False
    try:
        try:
            mic.start()
            mic_opened = True
        except Exception:
            status = "microphone-open-failed"
        else:
            try:
                # Do not reinterpret 24-bit, float or stereo as 16-bit PCM.
                if (mic.sample_rate != SAMPLE_RATE
                    or mic.channels != CHANNELS
                    or str(mic.format) != "int16"):
                    status = "format-unsupported"
                else:
                    print(_PREFIX + "capture-started", flush=True)
                    wav_bytes = _collect_ram_wav()
                    status = "capture-complete" if wav_bytes else "no-audio"
            except Exception:
                status = "capture-failed"
            finally:
                try:
                    mic.stop()
                    mic_opened = False
                except Exception:
                    status = "microphone-release-failed"

        if status == "capture-complete" and wav_bytes is not None:
            try:
                print(_PREFIX + _safe_signal_summary(wav_bytes), flush=True)
            except Exception:
                status = "signal-summary-failed"

        if status == "capture-complete" and wav_bytes is not None:
            try:
                # Official, separate finite-source ASR path; no custom Whisper
                # implementation or audio saved on disk.
                asr = WAVAutomaticSpeechRecognition(
                    wav=wav_bytes, language="sv", translate=False,
                )
                App.start_brick(asr)
                status = _private_label(asr.transcribe())
            except Exception:
                status = "wav-asr-failed"
    finally:
        if asr is not None:
            try:
                asr.cancel()
            except Exception:
                status = "wav-asr-cancel-failed"
        # Last-chance cleanup, including failures during capture.
        if mic_opened:
            try:
                mic.stop()
            except Exception:
                status = "microphone-release-failed"
        wav_bytes = None
        print(_PREFIX + status, flush=True)
        raise StopIteration


App.run(user_loop=run_one)
