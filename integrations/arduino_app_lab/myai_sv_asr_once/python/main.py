# SPDX-License-Identifier: MIT
"""One operator-triggered ASR session; read-only aggregate PCM level diagnostics.

This application is NEVER automatically started. Only a physical operator may
start it after separately approving a microphone session and coordinated service
pause. No PCM, voice, model response, or transcript is persisted or logged.
"""
from __future__ import annotations

import math
import re

import numpy as np
from arduino.app_bricks.asr import AutomaticSpeechRecognition
from arduino.app_peripherals.microphone import ALSAMicrophone
from arduino.app_utils import App


class MeteredMicrophone(ALSAMicrophone):
    """Observe the exact PCM chunks sent to the ASR reader; never extra capture."""

    def __init__(self) -> None:
        # Pinned, physically operator-verified Kraken V3 X card 1/device 0.
        # Fail closed if App Lab sees a different card; no fallback microphone.
        super().__init__(device="plughw:1,0", shared=False, auto_reconnect=False)
        self.sample_count = 0
        self.square_sum = 0.0
        self.peak = 0.0
        self._first_chunk_reported = False

    def capture(self):
        chunk = super().capture()
        if chunk is None or chunk.size == 0:
            return chunk
        # The SDK starts an ASR session before its reader calls capture().
        # This is the first observed PCM chunk, NOT confirmation that the
        # inference server or WebSocket has consumed it yet.
        if not self._first_chunk_reported:
            self._first_chunk_reported = True
            print("MYAI_ASR: pcm-first-chunk-speak-now", flush=True)
        # The ALSA Mic defaults to signed 16-bit PCM (16 kHz, mono).
        # Observe but NEVER alter the chunk forwarded by the ASR brick.
        samples = np.asarray(chunk, dtype=np.float64)
        self.sample_count += int(samples.size)
        self.square_sum += float(np.dot(samples, samples))
        self.peak = max(self.peak, float(np.max(np.abs(samples))))
        return chunk

    def level_status(self) -> str:
        if not self.sample_count:
            return "no-pcm"
        rms = math.sqrt(self.square_sum / self.sample_count) / 32768.0
        peak = self.peak / 32768.0
        # Coarse categories, not voice/activity detection. In particular a
        # 'present' level may be non-speech noise or feedback.
        if peak < 0.001 and rms < 0.001:
            return "near-silent"
        if rms < 0.0178:  # -35 dBFS
            return "low"
        return "present"


mic = MeteredMicrophone()
asr = AutomaticSpeechRecognition(mic=mic, language="sv")
_used = False


def run_one_diagnostic() -> None:
    global _used
    if _used:
        raise StopIteration
    _used = True
    status = "unavailable-or-failed"
    try:
        mic.start()
        print("MYAI_ASR: microphone-open-asr-pending", flush=True)
        recognized = asr.transcribe(duration=5)
        if not isinstance(recognized, str) or not recognized.strip():
            status = "no-final-text"
        else:
            cleaned = re.sub(r"[^a-z0-9åäö]+", " ", recognized.casefold()).strip()
            status = "reference-recognized" if cleaned == "vad heter du" else "other-nonempty-text"
    except Exception:
        # SDK exceptions may contain sensitive voice/model data; do not print.
        status = "unavailable-or-failed"
    finally:
        try:
            mic.stop()
        except Exception:
            status = "microphone-release-failed"
        print("MYAI_ASR: pcm-level-" + mic.level_status(), flush=True)
        print("MYAI_ASR: " + status, flush=True)
        raise StopIteration


App.run(user_loop=run_one_diagnostic)
