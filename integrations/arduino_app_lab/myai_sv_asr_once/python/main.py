# SPDX-License-Identifier: MIT
"""Manual App Lab diagnostic: one five-second Swedish ASR session, no LLM.

Do not start this App without fresh permission from everyone within range
of the microphone. Importing the file inside App Lab constructs the official
ASR Brick; only clicking Run starts the App and its microphone session.
All logs are fixed, non-content categories. No transcript is ever printed.
"""
from __future__ import annotations

from arduino.app_bricks.asr import AutomaticSpeechRecognition
from arduino.app_peripherals.microphone import Microphone
from arduino.app_utils import App

# Pin the ALSA pair used during the previous VENTUNO hardware smoke.
# Reconfirm identity inside App Lab before any human-authorized run:
# container card numbers may differ. Never fall back to another mic.
mic = Microphone(device="plughw:1,0", shared=False, auto_reconnect=False)
asr = AutomaticSpeechRecognition(mic=mic, language="sv")
_used = False


def run_one_diagnostic() -> None:
    global _used
    if _used:
        raise StopIteration
    _used = True
    status = "unavailable-or-failed"
    try:
        # With a caller-provided microphone, the official ASR Brick does
        # NOT start or stop it; the caller owns the peripheral lifecycle.
        mic.start()
        print("MYAI_ASR: capture-begins")
        recognized = asr.transcribe(duration=5)
        if not isinstance(recognized, str) or not recognized.strip():
            status = "no-final-text"
        else:
            # This is ONLY a diagnostic comparison, never MyAI's conversation
            # allowlist. Any harmless natural Swedish text can be forwarded
            # by the separate, explicitly opted-in read-only bridge.
            import re
            cleaned = re.sub(r"[^a-z0-9åäö]+", " ",
                             recognized.casefold()).strip()
            status = ("reference-recognized" if cleaned == "vad heter du"
                      else "other-nonempty-text")
    except Exception:
        # Do not publish exception messages; SDK errors may contain speech.
        status = "unavailable-or-failed"
    finally:
        try:
            mic.stop()
        except Exception:
            # An unsuccessful release must never be reported as a pass.
            status = "microphone-release-failed"
        print("MYAI_ASR: " + status)
        # The App.run lifecycle manages the ASR service; this caller
        # must release its injected microphone in all paths.
        raise StopIteration


App.run(user_loop=run_one_diagnostic)
