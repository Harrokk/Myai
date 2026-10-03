import struct

from modules.voice.frame_controller import (
    VoiceFrameController,
    create_frame_controller,
)
from modules.voice.vad import VoiceActivityDetector


def frame(value, samples=160):
    return struct.pack(
        "<" + "h" * samples,
        *([value] * samples),
    )


class FakeSession:
    def __init__(self):
        self.interrupt_calls = 0
        self.audio_calls = []

    def interrupt(self):
        self.interrupt_calls += 1
        return {
            "stopped": True,
            "reason": "test",
        }

    def handle_audio(self, audio):
        self.audio_calls.append(audio)
        return {
            "status": "completed",
            "bytes": len(audio),
        }


def detector():
    return VoiceActivityDetector(
        rms_threshold=500,
        start_frames=2,
        end_silence_frames=2,
    )


def test_silence_does_not_call_session():
    session = FakeSession()
    controller = VoiceFrameController(
        session,
        detector(),
        pre_roll_frames=2,
    )

    result = controller.process_frame(frame(0))

    assert result["event"] == "silence"
    assert session.interrupt_calls == 0
    assert session.audio_calls == []


def test_speech_start_interrupts_tts():
    session = FakeSession()
    controller = VoiceFrameController(
        session,
        detector(),
        pre_roll_frames=2,
    )

    controller.process_frame(frame(1000))
    result = controller.process_frame(frame(1000))

    assert result["event"] == "speech_start"
    assert session.interrupt_calls == 1
    assert controller.capturing is True


def test_speech_end_sends_one_buffered_utterance():
    session = FakeSession()
    controller = VoiceFrameController(
        session,
        detector(),
        pre_roll_frames=2,
    )
    first = frame(1000)
    second = frame(1100)
    third = frame(900)

    controller.process_frame(first)
    controller.process_frame(second)
    controller.process_frame(third)
    controller.process_frame(frame(0))
    result = controller.process_frame(frame(0))

    assert result["completed"] is True
    assert result["completion_reason"] == "speech_end"
    assert len(session.audio_calls) == 1
    audio = session.audio_calls[0]
    assert audio.startswith(first)
    assert second in audio
    assert third in audio
    assert result["session_result"]["status"] == "completed"


def test_max_duration_forces_completion():
    session = FakeSession()
    controller = VoiceFrameController(
        session,
        VoiceActivityDetector(
            rms_threshold=500,
            start_frames=1,
            end_silence_frames=10,
        ),
        pre_roll_frames=0,
        max_utterance_frames=3,
    )

    controller.process_frame(frame(1000))
    controller.process_frame(frame(1000))
    result = controller.process_frame(frame(1000))

    assert result["completed"] is True
    assert result["completion_reason"] == "max_duration"
    assert len(session.audio_calls) == 1


def test_controller_reset_clears_capture():
    session = FakeSession()
    controller = VoiceFrameController(
        session,
        VoiceActivityDetector(
            rms_threshold=500,
            start_frames=1,
            end_silence_frames=2,
        ),
    )
    controller.process_frame(frame(1000))

    controller.reset()

    assert controller.capturing is False
    assert session.audio_calls == []


def test_create_frame_controller_uses_settings():
    session = FakeSession()
    settings = {
        "voice": {
            "vad_rms_threshold": 700,
            "vad_start_frames": 3,
            "vad_end_silence_frames": 5,
            "vad_pre_roll_frames": 4,
            "vad_frame_ms": 20,
            "max_utterance_seconds": 10,
        }
    }

    controller = create_frame_controller(
        session,
        settings,
    )

    assert controller.vad.rms_threshold == 700
    assert controller.vad.start_frames == 3
    assert controller.pre_roll.maxlen == 4
    assert controller.max_utterance_frames == 500
