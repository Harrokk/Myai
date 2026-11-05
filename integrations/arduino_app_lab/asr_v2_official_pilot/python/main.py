# SPDX-License-Identifier: MIT
"""Operator-initiated official Arduino App Lab ASR v2 pilot.

THIS APP RECORDS only when the operator explicitly clicks Run in App Lab,
after separate authorization and resource-preflight review. Importing the
project in GitHub does not start an App Lab job. Never auto-deploy this app.

Uses Arduino's own managed microphone and Whisper Small ASR Brick; no ALSA
device hardcoding, PCM transforms, Python Whisper workers or MyAI services.
All recognized words stay private: logs show ONLY one fixed outcome label.
"""
from __future__ import annotations

import unicodedata

from arduino.app_bricks.asr import AutomaticSpeechRecognition
from arduino.app_utils import App

MAX_EVENTS = 64
MAX_WORD_CHARS = 240
MAX_SENTENCE_SECONDS = 8
_PREFIX = "MYAI_APP_LAB_ASR_V2: "
asr = AutomaticSpeechRecognition(language="sv", translate=False)
_used = False


def _private_label(raw: object) -> str:
    if not isinstance(raw, str):
        return "invalid-final"
    text = unicodedata.normalize("NFC", raw.strip())
    if not 1 <= len(text) <= MAX_WORD_CHARS:
        return "invalid-final"
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in text):
        return "invalid-final"
    normalized = " ".join(text.casefold().strip(" .,!?;:").split())
    if normalized == "vad heter du":
        return "reference-recognized"
    return "other-nonempty-final"


def run_one():
    """App Lab owns microphone start/stop; the ASR session is one-shot."""
    global _used
    if _used:
        raise StopIteration
    _used = True
    status = "no-final"
    count = 0
    try:
        with asr.transcribe_sentence_stream(timeout=MAX_SENTENCE_SECONDS) as stream:
            for event in stream:
                count += 1
                if count > MAX_EVENTS:
                    status = "event-budget-rejected"
                    break
                kind = getattr(event, "type", None)
                if kind == "partial_text":
                    continue  # Never inspect, log or forward partial words.
                if kind != "full_text":
                    status = "unexpected-event"
                    break
                status = _private_label(getattr(event, "data", None))
                break
    except Exception:
        # Vendor exceptions may include raw recognized words or file paths.
        status = "asr-session-failed"
    finally:
        try:
            asr.cancel()
        except Exception:
            status = "asr-cancel-failed"
        print(_PREFIX + status, flush=True)
        raise StopIteration  # Avoid more App.run turns or repeat recordings.


App.run(user_loop=run_one)
