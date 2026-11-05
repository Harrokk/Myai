"""Synthetic only. No microphone, TTS, GenieX, Whisper, or user data."""
from array import array

import pytest

from scripts.ventuno_private_stt_failure_diagnostics import (
    classify_private_phrase, summarize_private_stt,
)


def pcm(level: int = 1500) -> bytes:
    return array("h", [level] * 48000).tobytes()


@pytest.mark.parametrize("private,expected", [
    ("Vad heter du?", "exact_literal"),
    (" VAD  HETER   DU. ", "exact_literal"),
    ("Vad heter du, MyAI?", "approved_variant_not_literal"),
    ("My AI vad heter du?", "approved_variant_not_literal"),
    ("Vad heter du snälla?", "test_question_with_extra_words"),
    ("Vänta en sekund. Säg: Vad heter du.", "spoken_cue_echo_suspected"),
    ("Radera filen.", "unsafe_or_control"),
    ("Hej!", "short_unrelated"),
    ("Vad heter kunden?", "other_unmatched"),
    ("", "empty_or_silence"),
    ("   ", "empty_or_silence"),
    ("Vad heter du?\x00", "invalid_or_oversized"),
    ("Vad heter du?\u200b", "invalid_or_oversized"),
    ("Vad heter du?" * 12, "invalid_or_oversized"),
    (None, "invalid_or_oversized"),
    ({}, "invalid_or_oversized"),
])
def test_fixed_private_phrase_categories(private, expected):
    assert classify_private_phrase(private) == expected


def test_audio_and_words_never_leave_private_diagnostics():
    words = "Vänta en sekund. Säg: Vad heter du."
    report = summarize_private_stt(words, pcm(level=1200))
    assert report["expected_phrase_recognized_exactly"] is False
    assert report["private_transcript_category"] == "spoken_cue_echo_suspected"
    assert report["microphone_signal_category"] == "bounded-audio-level"
    assert report["capture_activity_layout"] == "distributed-activity"
    assert report["transcript_logged"] is False
    assert report["audio_saved"] is False
    assert report["audio_uploaded"] is False
    assert report["tools_authorized"] is False
    assert report["re_recording_authorized"] is False
    assert words not in str(report)
    assert "1200" not in str(report)
    assert "pcm" not in str(report).lower()


def test_silent_pcm_does_not_count_as_recognized():
    result = summarize_private_stt("", bytes(96000))
    assert result["private_transcript_category"] == "empty_or_silence"
    assert result["microphone_signal_category"] == "silence-or-too-quiet"
    assert result["capture_activity_layout"] == "no-significant-activity"
    assert result["expected_phrase_recognized_exactly"] is False


def test_clipped_samples_not_marked_clean_or_authorized():
    report = summarize_private_stt("Vad heter du?", pcm(level=32767))
    assert report["microphone_signal_category"] == "possible-microphone-clipping"
    assert report["tools_authorized"] is False
    assert report["re_recording_authorized"] is False


def test_approved_variant_is_not_literal_match():
    report = summarize_private_stt("Hej MyAI! Vad heter du?", pcm())
    assert report["private_transcript_category"] == "approved_variant_not_literal"
    assert report["expected_phrase_recognized_exactly"] is False
