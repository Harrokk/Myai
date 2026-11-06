# SPDX-License-Identifier: MIT
"""Manual-only Arduino ASR v2 pilot with an explicit ALSA USB microphone.

The previous default-mic App failed at Microphone(0) enumeration before ASR
could start. This version uses the known historical USB capture route as an
explicit device, but STILL requires a fresh read-only card-ID verification
before another operator-approved physical microphone session.

No legacy Whisper workers, external API, tool calls or service controls.
Only fixed outcome labels are printed, never recorded words or PCM.
A blank full_text event does not terminate a sentence; wait within the same
8-second stream for one nonempty final, without making another recording.
"""
from __future__ import annotations

import unicodedata

from arduino.app_bricks.asr import AutomaticSpeechRecognition
from arduino.app_peripherals.microphone import ALSAMicrophone
from arduino.app_utils import App

MAX_EVENTS = 64
MAX_WORD_CHARS = 240
MAX_SENTENCE_SECONDS = 8
MIC_DEVICE = "plughw:1,0"  # Host card 1:0 reconfirmed 2026-11-06.
_PREFIX = "MYAI_APP_LAB_ASR_V2: "

# Passing an explicit ALSA mic bypasses SDK's Microphone(0) auto-selection.
# Caller owns mic.start() and mic.stop(); App.run manages the ASR Brick.
mic = ALSAMicrophone(
    device=MIC_DEVICE, shared=False, auto_reconnect=False,
)
asr = AutomaticSpeechRecognition(mic=mic, language="sv", translate=False)
_used = False


def _private_label(raw: object) -> str:
    """Return only fixed categories; no words, counts or exception messages."""
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


def run_one():
    """Exactly one bounded ASR session after explicit operator action."""
    global _used
    if _used:
        raise StopIteration
    _used = True
    status = "no-final"
    count = 0
    mic_attempted = False
    try:
        mic_attempted = True
        try:
            mic.start()
        except Exception:
            # Never print vendor exception details or device identifiers.
            status = "microphone-open-failed"
        else:
            print(_PREFIX + "microphone-opened", flush=True)
            try:
                with asr.transcribe_sentence_stream(timeout=MAX_SENTENCE_SECONDS) as stream:
                    for event in stream:
                        count += 1
                        if count > MAX_EVENTS:
                            status = "event-budget-rejected"
                            break
                        kind = getattr(event, "type", None)
                        if kind == "partial_text":
                            continue
                        if kind != "full_text":
                            status = "unexpected-event"
                            break
                        raw = getattr(event, "data", None)
                        if isinstance(raw, str) and not raw.strip():
                            # Arduino's sentence stream normally completes on a
                            # NONEMPTY full_text. Blank full_text is not a
                            # transcript; continue SAME bounded ASR session.
                            status = "empty-final-only"
                            continue
                        status = _private_label(raw)
                        break
            except Exception:
                status = "asr-session-failed"
    finally:
        try:
            asr.cancel()
        except Exception:
            status = "asr-cancel-failed"
        if mic_attempted:
            try:
                mic.stop()
            except Exception:
                status = "microphone-release-failed"
        print(_PREFIX + status, flush=True)
        raise StopIteration


App.run(user_loop=run_one)
