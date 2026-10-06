from core.voice_activity import (
    VoiceActivityGate,
    VoiceStreamController,
)


def test_gate_starts_after_required_speech_frames():
    gate = VoiceActivityGate(
        start_speech_frames=2,
        end_silence_frames=2,
    )

    assert gate.feed(b"a", True) is None
    event = gate.feed(b"b", True)

    assert event["type"] == "speech_started"
    assert gate.state == "speaking"


def test_gate_finishes_after_required_silence():
    gate = VoiceActivityGate(
        start_speech_frames=1,
        end_silence_frames=2,
    )

    gate.feed(b"a", True)
    assert gate.feed(b"b", True) is None
    assert gate.feed(b"c", False) is None
    event = gate.feed(b"d", False)

    assert event["type"] == "utterance_complete"
    assert event["reason"] == "silence"
    assert event["frames"] == [
        b"a",
        b"b",
        b"c",
        b"d",
    ]
    assert gate.state == "idle"


def test_gate_resets_false_start():
    gate = VoiceActivityGate(
        start_speech_frames=2,
        end_silence_frames=2,
    )

    gate.feed(b"a", True)
    gate.feed(b"b", False)
    assert gate.state == "idle"

    assert gate.feed(b"c", True) is None
    event = gate.feed(b"d", True)

    assert event["type"] == "speech_started"


def test_gate_finishes_at_max_length():
    gate = VoiceActivityGate(
        start_speech_frames=1,
        end_silence_frames=5,
        max_frames=3,
    )

    gate.feed(b"a", True)
    assert gate.feed(b"b", True) is None
    event = gate.feed(b"c", True)

    assert event["type"] == "utterance_complete"
    assert event["reason"] == "max_length"


def test_invalid_speech_flag_is_rejected():
    gate = VoiceActivityGate()

    try:
        gate.feed(b"a", 1)
    except ValueError as error:
        assert "bool" in str(error)
    else:
        raise AssertionError("non-bool speech flag should fail")


class FakeVAD:
    def __init__(self, decisions):
        self.decisions = list(decisions)

    def is_speech(self, frame):
        return self.decisions.pop(0)


class FakePipeline:
    def __init__(self):
        self.interrupt_calls = 0
        self.audio = []

    def interrupt(self):
        self.interrupt_calls += 1
        return True

    def process_utterance(self, audio):
        self.audio.append(audio)
        return {
            "status": "completed",
            "transcript": "hej",
        }


def test_controller_interrupts_tts_when_speech_starts():
    controller = VoiceStreamController(
        vad=FakeVAD([True]),
        gate=VoiceActivityGate(
            start_speech_frames=1,
            end_silence_frames=2,
        ),
        pipeline=FakePipeline(),
    )

    event = controller.feed_frame(b"a")

    assert event["type"] == "speech_started"
    assert event["tts_interrupted"] is True
    assert controller.pipeline.interrupt_calls == 1


def test_controller_sends_completed_audio_to_pipeline():
    pipeline = FakePipeline()
    controller = VoiceStreamController(
        vad=FakeVAD(
            [True, True, False, False]
        ),
        gate=VoiceActivityGate(
            start_speech_frames=1,
            end_silence_frames=2,
        ),
        pipeline=pipeline,
    )

    controller.feed_frame(b"a")
    controller.feed_frame(b"b")
    controller.feed_frame(b"c")
    event = controller.feed_frame(b"d")

    assert event["type"] == "utterance_complete"
    assert pipeline.audio == [b"abcd"]
    assert event["pipeline_result"]["status"] == "completed"



def test_controller_calls_resource_handoff_around_inference():
    events = []
    pipeline = FakePipeline()
    controller = VoiceStreamController(
        vad=FakeVAD(
            [True, False, False]
        ),
        gate=VoiceActivityGate(
            start_speech_frames=1,
            end_silence_frames=2,
        ),
        pipeline=pipeline,
        before_process=lambda: events.append(
            "before"
        ),
        after_process=lambda: events.append(
            "after"
        ),
    )

    controller.feed_frame(b"a")
    controller.feed_frame(b"b")
    result = controller.feed_frame(b"c")

    assert result["type"] == "utterance_complete"
    assert events == [
        "before",
        "after",
    ]
    assert pipeline.audio == [b"abc"]


def test_controller_restores_resources_when_pipeline_fails():
    events = []

    class FailingPipeline(FakePipeline):
        def process_utterance(self, audio):
            raise RuntimeError(
                "inference-fel"
            )

    controller = VoiceStreamController(
        vad=FakeVAD(
            [True, False, False]
        ),
        gate=VoiceActivityGate(
            start_speech_frames=1,
            end_silence_frames=2,
        ),
        pipeline=FailingPipeline(),
        before_process=lambda: events.append(
            "before"
        ),
        after_process=lambda: events.append(
            "after"
        ),
    )

    controller.feed_frame(b"a")
    controller.feed_frame(b"b")

    try:
        controller.feed_frame(b"c")
    except RuntimeError as error:
        assert "inference-fel" in str(error)
    else:
        raise AssertionError(
            "Pipeline-felet skulle ha propagerats."
        )

    assert events == [
        "before",
        "after",
    ]
