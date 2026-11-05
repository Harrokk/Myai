"""Pure private one-shot Swedish STT mismatch diagnostics, no microphone.

Classifies one already-decoded transcript and a bounded in-memory PCM clip.
Only fixed labels are returned. No words, audio samples, text, command
permission, retries, network, model loading or device access.
"""
from __future__ import annotations

import unicodedata

from scripts.ventuno_usb_dialogue_once import (
    approved_short_question, classify_unapproved_question,
    classify_pcm_quality, classify_pcm_activity_layout,
)

TARGET = "vad heter du"
_PHRASES = frozenset((
    "exact_literal", "approved_variant_not_literal", "empty_or_silence",
    "test_question_with_extra_words", "spoken_cue_echo_suspected",
    "unsafe_or_control", "short_unrelated", "other_unmatched",
    "invalid_or_oversized",
))
_QUALITY = frozenset((
    "invalid-pcm", "silence-or-too-quiet",
    "possible-microphone-clipping", "low-microphone-level",
    "very-loud-microphone-level", "bounded-audio-level",
))
_ACTIVITY = frozenset((
    "invalid-pcm", "no-significant-activity", "early-activity",
    "middle-activity", "late-activity", "distributed-activity",
))


def classify_private_phrase(words: object) -> str:
    if not isinstance(words, str) or len(words) > 96:
        return "invalid_or_oversized"
    if any(unicodedata.category(c) in ("Cc", "Cf", "Cs") for c in words):
        return "invalid_or_oversized"
    normalized = unicodedata.normalize("NFC", words).casefold()
    normalized = " ".join(normalized.strip(" \t\n\r.,!?;:").split())
    if not normalized:
        return "empty_or_silence"
    if normalized == TARGET:
        return "exact_literal"
    if approved_short_question(words) == TARGET:
        return "approved_variant_not_literal"
    source = classify_unapproved_question(words)
    categories = {
        "empty-or-silence": "empty_or_silence",
        "invalid-or-oversize": "invalid_or_oversized",
        "unsafe-command-or-control": "unsafe_or_control",
        "spoken-cue-echo-suspected": "spoken_cue_echo_suspected",
        "test-question-with-extra-words": "test_question_with_extra_words",
        "unrelated-short-utterance": "short_unrelated",
        "other-unmatched-utterance": "other_unmatched",
    }
    return categories.get(source, "other_unmatched")


def summarize_private_stt(words: object, pcm: object) -> dict[str, object]:
    phrase = classify_private_phrase(words)
    quality = classify_pcm_quality(pcm)
    activity = classify_pcm_activity_layout(pcm)
    if phrase not in _PHRASES or quality not in _QUALITY or activity not in _ACTIVITY:
        raise ValueError("unexpected-private-stt-category")
    return {
        "expected_phrase_recognized_exactly": phrase == "exact_literal",
        "private_transcript_category": phrase,
        "microphone_signal_category": quality,
        "capture_activity_layout": activity,
        "transcript_logged": False,
        "audio_saved": False,
        "audio_uploaded": False,
        "tools_authorized": False,
        "re_recording_authorized": False,
    }
