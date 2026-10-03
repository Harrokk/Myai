import struct

import pytest

from modules.voice import vad


def frame(value, samples=160):
    return struct.pack(
        "<" + "h" * samples,
        *([value] * samples),
    )


def test_pcm16_rms_for_silence_is_zero():
    assert vad.pcm16_rms(frame(0)) == 0


def test_pcm16_rms_matches_constant_amplitude():
    assert vad.pcm16_rms(frame(1000)) == pytest.approx(1000)


def test_pcm16_rejects_odd_byte_length():
    with pytest.raises(ValueError):
        vad.pcm16_rms(b"\x00")


def test_vad_requires_consecutive_start_frames():
    detector = vad.VoiceActivityDetector(
        rms_threshold=500,
        start_frames=2,
        end_silence_frames=2,
    )

    first = detector.process_frame(frame(1000))
    second = detector.process_frame(frame(1000))

    assert first["event"] == "silence"
    assert second["event"] == "speech_start"
    assert detector.speaking is True


def test_vad_ends_after_configured_silence():
    detector = vad.VoiceActivityDetector(
        rms_threshold=500,
        start_frames=1,
        end_silence_frames=2,
    )

    start = detector.process_frame(frame(1000))
    middle = detector.process_frame(frame(0))
    end = detector.process_frame(frame(0))

    assert start["event"] == "speech_start"
    assert middle["event"] == "speech"
    assert end["event"] == "speech_end"
    assert detector.speaking is False


def test_short_noise_burst_does_not_start_speech():
    detector = vad.VoiceActivityDetector(
        rms_threshold=500,
        start_frames=2,
        end_silence_frames=2,
    )

    detector.process_frame(frame(1000))
    result = detector.process_frame(frame(0))

    assert result["event"] == "silence"
    assert detector.speaking is False


def test_reset_clears_state():
    detector = vad.VoiceActivityDetector(
        rms_threshold=500,
        start_frames=1,
        end_silence_frames=2,
    )
    detector.process_frame(frame(1000))

    detector.reset()

    assert detector.speaking is False


def test_create_vad_from_settings():
    detector = vad.create_vad_from_settings(
        {
            "voice": {
                "vad_rms_threshold": 700,
                "vad_start_frames": 3,
                "vad_end_silence_frames": 6,
            }
        }
    )

    assert detector.rms_threshold == 700
    assert detector.start_frames == 3
    assert detector.end_silence_frames == 6
