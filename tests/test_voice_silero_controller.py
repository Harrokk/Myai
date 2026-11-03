"""Mock-only contracts for the opt-in Silero→VoiceSession integration.

No real ALSA, microphone, user audio or ONNX model is ever imported.
"""
from types import SimpleNamespace

import pytest

from core.voice_silero_controller import SileroVoiceStreamController
from core.voice_session import VoiceSession


class FakeSegmenter:
    def __init__(self, entries=()):
        self.entries = list(entries)
        self.active = False
        self.reset_calls = 0

    def feed(self, frame):
        if len(frame) != 640:
            raise ValueError("Not 20ms")
        active, segments = self.entries.pop(0) if self.entries else (False, [])
        self.active = active
        return segments

    def is_speech_detected(self):
        return self.active

    def reset(self):
        self.active = False
        self.reset_calls += 1


class FakePipeline:
    def __init__(self, fail=False):
        self.fail = fail
        self.interrupts = 0
        self.audio = []

    def interrupt(self):
        self.interrupts += 1
        return True

    def process_utterance(self, audio):
        self.audio.append(audio)
        if self.fail:
            raise RuntimeError("synthetic-llm-error")
        return {"status": "completed"}


def controller(segmenter, pipeline=None, **kwargs):
    return SileroVoiceStreamController(
        vad=segmenter, pipeline=pipeline or FakePipeline(), **kwargs
    )


def test_started_event_interrupts_tts_once_and_ends_after_complete_segment():
    pcm = b"\x01\x00" * 400
    vad = FakeSegmenter([(True, []), (True, []), (False, [pcm])])
    pipe = FakePipeline()
    events = []
    c = controller(
        vad, pipe, before_process=lambda: events.append("before"),
        after_process=lambda: events.append("after")
    )
    started = c.feed_frame(bytes(640))
    assert started == {"type": "speech_started", "tts_interrupted": True}
    assert c.feed_frame(bytes(640)) is None
    completed = c.feed_frame(bytes(640))
    assert completed["type"] == "utterance_complete"
    assert completed["reason"] == "silero_endpoint"
    assert completed["pipeline_result"]["status"] == "completed"
    assert pipe.audio == [pcm]
    assert pipe.interrupts == 1
    assert events == ["before", "after"]
    assert vad.reset_calls == 1


def test_segment_arriving_before_onset_event_interrupts_before_processing():
    vad = FakeSegmenter([(False, [bytes(640)])])
    pipe = FakePipeline()
    done = controller(vad, pipe).feed_frame(bytes(640))
    assert done["type"] == "utterance_complete"
    assert pipe.interrupts == 1


def test_after_process_and_vad_reset_even_if_inference_raises():
    pipe = FakePipeline(fail=True)
    vad = FakeSegmenter([(True, [bytes(640)])])
    called = []
    c = controller(
        vad, pipe,
        before_process=lambda: called.append("before"),
        after_process=lambda: called.append("after"),
    )
    with pytest.raises(RuntimeError, match="synthetic-llm-error"):
        c.feed_frame(bytes(640))
    assert called == ["before", "after"]
    assert vad.reset_calls == 1


@pytest.mark.parametrize("invalid", [
    [(True, [b""])], [(True, [b"\x00"])],
    [(True, [b"\x00" * (13 * 16000 * 2 + 2)])],
    [(True, ["not-bytes"])],
    [(True, [bytes(640), bytes(640)])],
])
def test_invalid_or_multiple_segments_never_call_stt(invalid):
    vad = FakeSegmenter(invalid)
    pipe = FakePipeline()
    with pytest.raises(ValueError):
        controller(vad, pipe).feed_frame(bytes(640))
    assert pipe.audio == []


def test_unexpected_segment_collection_fails_closed():
    class Bad(FakeSegmenter):
        def feed(self, frame):
            return "invalid"
    pipe = FakePipeline()
    with pytest.raises(ValueError):
        controller(Bad(), pipe).feed_frame(bytes(640))
    assert pipe.audio == []


class Mic:
    def __init__(self):
        self.reads = 0
        self.starts = 0
        self.stops = 0

    def start(self):
        self.starts += 1
        return True

    def stop(self):
        self.stops += 1
        return True

    def read_frame(self):
        self.reads += 1
        return {"frame": bytes(640), "overflowed": False}


class STT:
    def __init__(self):
        self.calls = []

    def transcribe(self, pcm):
        self.calls.append(pcm)
        return {"text": "Vad heter du?", "confidence": 0.99, "language": "sv"}


class Assistant:
    def __init__(self):
        self.messages = []

    def respond(self, message):
        self.messages.append(message)
        return {"answer": "Jag heter MyAI.", "tools": [], "tool_results": {}}


def voice_session(vad, mic=None, stt=None, tts=None, *, overrides=None):
    mic = mic or Mic()
    stt = stt or STT()
    cfg = {"enabled": True, "tts_enabled": False,
           "vad_provider": "sherpa_silero_segments",
           "redundancy_enabled": False, "session_max_wait_frames": 4}
    cfg.update(overrides or {})
    assistant = Assistant()
    return VoiceSession(
        assistant,
        settings={"voice": cfg},
        components={
            "enabled": True, "microphone": mic,
            "vad": vad, "primary_stt": stt, "backup_stt": [], "tts": tts,
        },
    ), assistant, mic, stt


def test_voice_session_routes_silero_to_stt_and_existing_assistant():
    vad = FakeSegmenter([(True, []), (False, [bytes(640)])])
    session, assistant, mic, stt = voice_session(vad)
    assert isinstance(session.controller, SileroVoiceStreamController)
    result = session.run_once()
    assert result["status"] == "utterance_complete"
    assert result["end_reason"] == "silero_endpoint"
    assert stt.calls == [bytes(640)]
    assert assistant.messages == ["Vad heter du?"]
    assert mic.starts == 1
    assert vad.reset_calls >= 2  # session start and utterance completion


def test_voice_session_timeout_clears_silero_buffer_not_transcribed():
    vad = FakeSegmenter([(True, []), (True, [])])
    session, assistant, mic, stt = voice_session(vad)
    outcome = session.run_once(max_wait_frames=2)
    assert outcome["status"] == "timeout"
    assert vad.reset_calls >= 2
    assert stt.calls == [] and assistant.messages == []
    assert session.stop() is True
    assert mic.stops == 1
    assert vad.reset_calls >= 3


def test_factory_instantiates_silero_and_parakeet_only_by_explicit_opt_in():
    from core.voice_factory import build_voice_components
    from modules.voice.sherpa_silero_segments import SherpaSileroSegments
    from modules.voice.sherpa_onnx_provider import SherpaOnnxParakeetSTT

    class FakeHardware:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    providers = {
        "microphone": {"sounddevice": FakeHardware},
        "vad": {"webrtcvad": FakeHardware,
                "sherpa_silero_segments": SherpaSileroSegments},
        "stt": {"faster_whisper": FakeHardware,
                "sherpa_onnx_parakeet": SherpaOnnxParakeetSTT},
        "tts": {"pyttsx3": FakeHardware},
    }
    voice = {
        "enabled": True, "tts_enabled": False,
        "vad_provider": "sherpa_silero_segments",
        "silero_model_path": "/approved/local/silero_vad.onnx",
        "stt_provider": "sherpa_onnx_parakeet",
        "stt_model": "/approved/local/parakeet",
        "stt_device": "cpu", "stt_compute_type": "int8",
    }
    built = build_voice_components(
        settings={"voice": voice}, provider_classes=providers)
    assert isinstance(built["vad"], SherpaSileroSegments)
    assert built["vad"].model_path == voice["silero_model_path"]
    assert built["vad"]._vad is None
    assert isinstance(built["primary_stt"], SherpaOnnxParakeetSTT)
    assert built["primary_stt"]._model is None


@pytest.mark.parametrize("change", [
    {"silero_model_path": ""}, {"sample_rate": 48000},
    {"channels": 2}, {"frame_ms": 30}, {"sample_width": 4},
    {"stt_provider": "faster_whisper"}
])
def test_factory_rejects_unreviewed_silero_modes(change):
    from core.voice_factory import build_voice_components

    class FakeHardware:
        def __init__(self, **kwargs):
            pass

    classes = {
        "microphone": {"sounddevice": FakeHardware},
        "vad": {"sherpa_silero_segments": FakeHardware},
        "stt": {"faster_whisper": FakeHardware,
                "sherpa_onnx_parakeet": FakeHardware},
        "tts": {"pyttsx3": FakeHardware},
    }
    voice = {
        "enabled": True, "tts_enabled": False,
        "vad_provider": "sherpa_silero_segments",
        "stt_provider": "sherpa_onnx_parakeet",
        "silero_model_path": "/local/silero_vad.onnx",
    }
    voice.update(change)
    with pytest.raises(ValueError):
        build_voice_components(settings={"voice": voice}, provider_classes=classes)


def test_voice_session_disabled_still_does_not_load_silero():
    from core.voice_factory import build_voice_components

    built = build_voice_components(settings={
        "voice": {"enabled": False,
                  "vad_provider": "sherpa_silero_segments",
                  "stt_provider": "sherpa_onnx_parakeet"}
    })
    assert built["enabled"] is False and built["vad"] is None


def test_full_synthetic_silero_stt_assistant_piper_speaker_chain_without_hardware():
    """Exercise existing pipeline with fake native VAD/STT/TTS and an in-memory WAV."""
    import io
    import wave
    from modules.voice.piper_alma_provider import PiperAlmaTTS

    class FakeVoice:
        def synthesize_wav(self, text, output, *, syn_config):
            assert text == "Jag heter MyAI."
            output.setnchannels(1)
            output.setsampwidth(2)
            output.setframerate(22050)
            output.writeframes(bytes(22050 * 2))

    class SynthModule:
        @staticmethod
        def SynthesisConfig(**kw):
            return SimpleNamespace(**kw)

    class FakeSink:
        def __init__(self):
            self.audio = []
        def reset(self):
            pass
        def play_wav(self, payload):
            with wave.open(io.BytesIO(payload), "rb") as reader:
                assert reader.getframerate() == 22050
            self.audio.append(payload)
            return True
        def stop(self):
            return True

    sink = FakeSink()
    piper = PiperAlmaTTS(voice=FakeVoice(), module=SynthModule, sink=sink)
    vad = FakeSegmenter([(True, []), (False, [bytes(640)])])
    session, assistant, mic, stt = voice_session(
        vad, tts=piper, overrides={"tts_enabled": True}
    )
    outcome = session.run_once()
    assert outcome["status"] == "utterance_complete"
    assert assistant.messages == ["Vad heter du?"]
    assert len(stt.calls) == 1
    assert len(sink.audio) == 1
    assert outcome["voice_result"]["status"] == "completed"
