"""One-shot USB voice dialog controller; secure stage boundaries.

This module does not itself open any audio device or load a model.
A future independently authorized hardware driver must supply bounded
capture, local Whisper, read-only GenieX, offline TTS, and ALSA playback
ports. The controller always rejects unsupported/unsafe transcriptions
and requires independent user consent for both recording and playback.
No transcript, LLM reply, raw audio or device label enters its report.
"""
from __future__ import annotations

import array
import io
import math
import re
import sys
import wave
from dataclasses import dataclass
from typing import Callable

from core.voice_pipeline import classify_voice_risk, normalize_transcript
from scripts.ventuno_usb_speaker_smoke import quiet_wav_from_tts

CAPTURE_BYTES = 3 * 16000 * 2
MAX_RESPONSE_CHARS = 120
MIN_CAPTURE_RMS = 0.001
APPROVED_QUESTIONS = frozenset((
    "vad heter du",
    "hur mår du",
    "hej my ai",
    "hej myai",
    "vad kan du göra",
))

# Small, literal aliases only. No fuzzy substring matching or arbitrary
# suffixes: the first physical test stopped on a mismatched short phrase,
# but its private transcript was discarded, so the cause is unknown.
# These are plausible harmless recognizer surface forms, not an assertion
# about what the user said or what Whisper decoded.
SAFE_QUESTION_ALIASES = {
    "vad heter du my ai": "vad heter du",
    "vad heter du myai": "vad heter du",
    "my ai vad heter du": "vad heter du",
    "myai vad heter du": "vad heter du",
    "hej my ai vad heter du": "vad heter du",
    "hej myai vad heter du": "vad heter du",
}



@dataclass
class DialogPorts:
    """Provided explicitly by a separately approved, audited driver."""
    capture: Callable[[], bytes]
    transcribe_local: Callable[[bytes], str]
    answer_local: Callable[[str], str]
    synthesize_local: Callable[[str], bytes]
    play_usb: Callable[[bytes], bool]
    fresh_readiness: Callable[[], dict[str, object]]
    available_ram_kib: Callable[[], int | None]
    audible_start_cue: Callable[[], bool] | None = None


def approved_short_question(text: object) -> str | None:
    if not isinstance(text, str) or not 1 <= len(text) <= 96:
        return None
    if "--" in text or any(ord(ch) < 32 for ch in text):
        return None
    normalized = normalize_transcript(text)
    if classify_voice_risk(text).get("level") != "low":
        return None
    if normalized in APPROVED_QUESTIONS:
        return normalized
    return SAFE_QUESTION_ALIASES.get(normalized)


def classify_unapproved_question(text: object) -> str:
    """Allowlisted failure categories only. Never publish recognized words."""
    if not isinstance(text, str) or not text.strip():
        return "empty-or-silence"
    if len(text) > 96 or any(ord(ch) < 32 for ch in text):
        return "invalid-or-oversize"
    normalized = normalize_transcript(text)
    if classify_voice_risk(text).get("level") != "low" or "--" in text:
        return "unsafe-command-or-control"
    if approved_short_question(text) is not None:
        return "approved"
    words = normalized.split()
    if (words and words[0] in ("säg", "sag")
            and "vad heter du" in normalized):
        return "spoken-cue-echo-suspected"
    if any(question in normalized for question in APPROVED_QUESTIONS):
        return "test-question-with-extra-words"
    if len(words) <= 2:
        return "unrelated-short-utterance"
    return "other-unmatched-utterance"


def pcm_signal_ok(raw: object) -> bool:
    if not isinstance(raw, bytes) or len(raw) != CAPTURE_BYTES:
        return False
    samples = array.array("h")
    samples.frombytes(raw)
    if sys.byteorder != "little":
        samples.byteswap()
    if len(samples) != 48000:
        return False
    rms = math.sqrt(sum(int(s) ** 2 for s in samples) / len(samples)) / 32768
    return math.isfinite(rms) and rms >= MIN_CAPTURE_RMS


def classify_pcm_quality(raw: object) -> str:
    """Coarse PCM-only diagnostics: no waveform, timestamps, or speech text."""
    if not isinstance(raw, bytes) or len(raw) != CAPTURE_BYTES:
        return "invalid-pcm"
    values = array.array("h")
    values.frombytes(raw)
    if sys.byteorder != "little":
        values.byteswap()
    if len(values) != 48000:
        return "invalid-pcm"
    power = sum(int(s) ** 2 for s in values) / len(values)
    rms = math.sqrt(power) / 32768
    if not math.isfinite(rms) or rms < MIN_CAPTURE_RMS:
        return "silence-or-too-quiet"
    clipped = sum(abs(int(s)) >= 32000 for s in values)
    if clipped > len(values) // 50:
        return "possible-microphone-clipping"
    if rms < 0.01:
        return "low-microphone-level"
    if rms > 0.35:
        return "very-loud-microphone-level"
    return "bounded-audio-level"


def clean_reply(reply: object) -> str | None:
    if not isinstance(reply, str):
        return None
    value = reply.strip()
    if not 1 <= len(value) <= MAX_RESPONSE_CHARS:
        return None
    if any(ord(ch) < 32 and ch not in "\n\t" for ch in value):
        return None
    if len(value.split()) > 18:
        return None
    return value


def readiness_ok(snapshot: object) -> bool:
    if not isinstance(snapshot, dict):
        return False
    return (
        snapshot.get("status") == "ready-for-separate-consented-dialogue-test"
        and snapshot.get("services_active") is True
        and snapshot.get("production_voice_disabled") is True
        and snapshot.get("usb_capture_and_playback_1_0_accessible") is True
        and snapshot.get("ram_gate_passed") is True
        and snapshot.get("disk_gate_passed") is True
    )


class OneShotUsbDialog:
    def __init__(self, ports: DialogPorts):
        self._ports = ports
        self._used = False

    def run(self, *, consent_to_record: bool = False,
            consent_to_play: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "status": "not-authorized",
            "recording_attempted": False,
            "transcription_verified": False,
            "local_geniex_answer_verified": False,
            "swedish_tts_verified": False,
            "playback_attempted": False,
            "playback_completed": False,
            "microphone_audio_saved": False,
            "microphone_audio_transmitted": False,
            "transcript_logged": False,
            "geniex_reply_logged": False,
            "generated_wav_saved": False,
            "production_changed": False,
            "repeat_attempt_allowed": False,
        }
        if self._used:
            result["status"] = "reject-second-attempt"
            return result
        if not (consent_to_record and consent_to_play):
            return result
        # Mark consumed before touching any external service or device.
        self._used = True
        if not readiness_ok(self._ports.fresh_readiness()):
            result["status"] = "reject-unsafe-hardware-or-resource-readiness"
            return result
        try:
            if self._ports.audible_start_cue is not None:
                # A short, capped audible Swedish cue marks the EXACT
                # beginning of the otherwise silent three-second capture.
                # The cue must finish before the microphone is opened.
                if self._ports.audible_start_cue() is not True:
                    result["status"] = "reject-audible-start-cue-failed"
                    return result
            result["recording_attempted"] = True
            pcm = self._ports.capture()
            result["capture_signal_class"] = classify_pcm_quality(pcm)
            if not pcm_signal_ok(pcm):
                result["status"] = "reject-weak-or-invalid-3s-capture"
                return result
            words = self._ports.transcribe_local(pcm)
            normalized = approved_short_question(words)
            if normalized is None:
                result["status"] = "reject-unapproved-or-unclear-test-utterance"
                result["unmatched_category"] = classify_unapproved_question(words)
                return result
            result["transcription_verified"] = True
            # Exit from this phase before asking the running language model.
            del pcm
            from scripts.ventuno_whisper_tiny_cpu_smoke import MIN_MEM_AVAILABLE_KIB
            memory = self._ports.available_ram_kib()
            if (type(memory) is not int or memory < MIN_MEM_AVAILABLE_KIB):
                result["status"] = "reject-ram-after-whisper"
                return result
            reply = clean_reply(self._ports.answer_local(normalized))
            if reply is None:
                result["status"] = "reject-unsafe-local-model-reply"
                return result
            result["local_geniex_answer_verified"] = True
            synthesis = self._ports.synthesize_local(reply)
            del reply
            capped, _info = quiet_wav_from_tts(synthesis)
            del synthesis
            if capped is None:
                result["status"] = "reject-unbounded-or-invalid-tts"
                return result
            result["swedish_tts_verified"] = True
            if not readiness_ok(self._ports.fresh_readiness()):
                result["status"] = "reject-hardware-changed-before-playback"
                return result
            result["playback_attempted"] = True
            if self._ports.play_usb(capped) is not True:
                result["status"] = "alsa-playback-not-confirmed"
                return result
            result["playback_completed"] = True
            # This reports ALSA command completion, not human hearing.
            result["status"] = "one-shot-usb-dialogue-alsa-playback-completed"
        except (OSError, ValueError, TypeError, RuntimeError, TimeoutError):
            result["status"] = "one-shot-dialogue-stage-failed"
        return result
