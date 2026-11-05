"""Independent, source-only App Lab ASR event boundary for future integration.

This module is intentionally independent of the legacy USB PCM/Whisper
experiments. It processes *already supplied* final ASR text in memory.
No audio device, API, filesystem, speech model, core tool or process access.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from threading import Lock
import unicodedata

TRACK_ID = "arduino_app_lab_asr_v2"
MAX_FINAL_CHARS = 240
_CUE_PREFIX = "vänta en sekund säg"


@dataclass(frozen=True)
class PrivateASRFinal:
    """Private words never appear in repr; do not log or serialize this value."""

    text: str = field(repr=False)


def check_disabled_track_config(config: object) -> bool:
    """Accept one explicit inactive, source-only mode. Never enables a backend."""
    expected = {
        "schema_version": 1,
        "track": TRACK_ID,
        "enabled": False,
        "legacy_pcm_whisper_enabled": False,
        "microphone_capture_enabled": False,
        "local_model_queries_enabled": False,
        "tool_dispatch_enabled": False,
        "service_control_enabled": False,
        "mode": "source_only",
    }
    if type(config) is not dict or set(config) != set(expected):
        raise ValueError("asr-track-configuration-unrecognized")
    for key, value in expected.items():
        if type(config[key]) is not type(value) or config[key] != value:
            raise ValueError("asr-track-configuration-is-not-disabled")
    return True


def _private_final_text(kind: object, value: object) -> PrivateASRFinal | None:
    if kind != "full_text" or not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFC", value.strip())
    if not 1 <= len(text) <= MAX_FINAL_CHARS:
        return None
    if any(unicodedata.category(char) in ("Cc", "Cf", "Cs") for char in text):
        return None
    compact = " ".join(text.casefold().split())
    if compact.startswith(_CUE_PREFIX):
        return None
    return PrivateASRFinal(text)


class FinalTextOneShotGate:
    """Pure ASR event consumer, not a recorder or runtime authorization.

    Explicit arming only accepts a future separately authorized UI action.
    Partial events are ignored; the first final event consumes the gate
    even when the text is invalid. No model or command execution exists.
    """

    def __init__(self):
        self._lock = Lock()
        self._armed = False
        self._used = False

    def arm_once(self, *, explicit_ui_action: bool = False) -> bool:
        with self._lock:
            if explicit_ui_action is not True or self._used or self._armed:
                return False
            self._armed = True
            return True

    def consume(self, kind: object, value: object) -> PrivateASRFinal | None:
        with self._lock:
            if not self._armed or self._used or kind != "full_text":
                return None
            self._used = True
            self._armed = False
        return _private_final_text(kind, value)

    def cancel(self) -> None:
        with self._lock:
            self._used = True
            self._armed = False
