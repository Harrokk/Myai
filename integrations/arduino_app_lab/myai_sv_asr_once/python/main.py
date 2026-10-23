# SPDX-License-Identifier: MIT
"""Manual App Lab diagnostic: one five-second Swedish ASR session, no LLM.

Do not start this App without fresh permission from everyone within range
of the microphone. Importing the file inside App Lab constructs the official
ASR Brick; only clicking Run starts the App and its microphone session.
All logs are fixed, non-content categories. No transcript is ever printed.
"""
from __future__ import annotations

from arduino.app_bricks.asr import AutomaticSpeechRecognition
from arduino.app_utils import App

asr = AutomaticSpeechRecognition(language="sv")
_used = False


def run_one_diagnostic() -> None:
    global _used
    if _used:
        raise StopIteration
    _used = True
    print("MYAI_ASR: capture-begins")
    try:
        # Official first-party API controls the microphone and ASR model.
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
        print("MYAI_ASR: " + status)
    except Exception:
        # Do not publish exception messages; SDK errors may contain speech.
        print("MYAI_ASR: unavailable-or-failed")
    finally:
        # The App.run lifecycle owns ASR startup/shutdown. Explicitly
        # end this user_loop after exactly one transcription attempt.
        raise StopIteration


App.run(user_loop=run_one_diagnostic)
