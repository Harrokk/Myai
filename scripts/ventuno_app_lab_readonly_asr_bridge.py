"""Source-only adapter for Arduino App Lab ASR final text -> local read-only GenieX.

Importing this module never opens an audio device, creates a network client,
starts an LLM, logs a transcript, saves a file or enables voice in production.
An App Lab operator must explicitly initiate ONE session in a separate,
approved application; this module does not initiate any physical capture.
"""
from __future__ import annotations

from dataclasses import dataclass, field
import threading
import unicodedata

from core.voice_pipeline import classify_voice_risk, normalize_transcript

MAX_FINAL_TEXT_CHARS = 240
MAX_REPLY_CHARS = 280
GENIEX_LOOPBACK_URL = "http://127.0.0.1:18181/v1"
_CUE_PREFIX = "vänta en sekund säg"


@dataclass(frozen=True)
class ReadOnlyASRTurn:
    """Raw words remain in process memory only and never enter repr/logs."""
    text: str = field(repr=False)


def read_final_asr_chunk(kind: object, text: object, *,
                         user_initiated: bool = False) -> ReadOnlyASRTurn | None:
    """Accept only an explicitly solicited, bounded final_text ASR segment.

    The official Arduino example emits partial_text and full_text; no
    preliminary hypothesis is allowed to call an LLM. This isn't a general
    command interpreter and cannot authorize tools or system writes.
    """
    if user_initiated is not True or kind != "full_text":
        return None
    if not isinstance(text, str):
        return None
    value = unicodedata.normalize("NFC", text.strip())
    if not 1 <= len(value) <= MAX_FINAL_TEXT_CHARS:
        return None
    if any(unicodedata.category(character) in ("Cc", "Cf", "Cs")
           for character in value):
        return None
    normalized = normalize_transcript(value)
    if not normalized or normalized.startswith(_CUE_PREFIX):
        return None
    # Conservative first-pass barrier. Structural tool isolation below is
    # the real protection; this textual heuristic is not a safety proof.
    if classify_voice_risk(value).get("level") != "low":
        return None
    return ReadOnlyASRTurn(value)


class ArduinoASROneShotGate:
    """One deliberately armed final chunk; no continuous-listening loop."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._armed = False
        self._used = False

    def arm_once(self, *, explicit_user_action: bool = False) -> bool:
        with self._lock:
            if explicit_user_action is not True or self._armed or self._used:
                return False
            self._armed = True
            return True

    def consume(self, kind: object, text: object) -> ReadOnlyASRTurn | None:
        with self._lock:
            if not self._armed or self._used or kind != "full_text":
                return None
            # Consume even if the transcript fails validation; never retry.
            self._used = True
            self._armed = False
        return read_final_asr_chunk(kind, text, user_initiated=True)

    def cancel(self) -> None:
        with self._lock:
            # Cancellation cannot re-arm a spent or running one-shot.
            self._armed = False
            self._used = True


def answer_readonly_geniex(turn: ReadOnlyASRTurn, client: object, *,
                           permit_local_model_query: bool = False) -> str:
    """One local LLM read-only answer, explicitly opted-in by caller.

    Only GenieXClient.chat(messages,timeout=...) is used: no MyAICore,
    planner, tool registry, memory writes or playback. The actual client
    must be constructed via MyAI's validated local GenieX factory.
    """
    if permit_local_model_query is not True:
        raise PermissionError("local-model-query-not-authorized")
    if type(turn) is not ReadOnlyASRTurn:
        raise ValueError("invalid-final-asr-turn")
    if (getattr(client, "provider_name", None) != "geniex"
            or getattr(client, "base_url", None) != GENIEX_LOOPBACK_URL):
        raise ValueError("non-local-or-unapproved-geniex-client")
    chat = getattr(client, "chat", None)
    if not callable(chat):
        raise ValueError("missing-geniex-chat")
    response = chat([
        {"role": "system", "content": (
            "Du är MyAI. Svara kort på svenska. Detta är ett isolerat "
            "läs- och samtalstest. Du kan inte använda verktyg, utföra "
            "kommandon, ändra filer, göra köp eller ändra systemet."
        )},
        {"role": "user", "content": turn.text},
    ], timeout=45)
    if not isinstance(response, str):
        raise ValueError("invalid-local-reply")
    answer = response.strip()
    if (not 1 <= len(answer) <= MAX_REPLY_CHARS
            or len(answer.split()) > 50
            or any(unicodedata.category(c) in ("Cc", "Cf", "Cs")
                   for c in answer)):
        raise ValueError("unbounded-or-unsafe-local-reply")
    return answer
