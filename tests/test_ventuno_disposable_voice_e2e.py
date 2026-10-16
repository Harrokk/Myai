"""VoicePipeline end-to-end with fixed synthetic PCM and pure fake providers.

No microphone/speaker, model import, network, SQLite or production file.
This tests STT -> safe synthetic response -> TTS -> Stop / failure.
"""
from core.voice_pipeline import VoicePipeline


SYNTHETIC_PCM = b"\x00\x00" * 640
SYNTHETIC_TRANSCRIPT = "Hej MyAI"


class DummySTT:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = 0

    def transcribe(self, audio):
        assert audio == SYNTHETIC_PCM
        self.calls += 1
        if self.fail:
            raise RuntimeError("PRIVATE_STT_ERROR_MUST_NOT_ESCAPE")
        return {"text": SYNTHETIC_TRANSCRIPT, "confidence": 0.99, "language": "sv"}


class DummyAssistant:
    def __init__(self):
        self.messages = []

    def respond(self, message):
        self.messages.append(message)
        return {"answer": "Detta är ett syntetiskt svar.",
                "tools": [], "tool_results": {}}


class DummyTTS:
    def __init__(self):
        self.utterances = []
        self.stopped = False

    def speak(self, text):
        self.utterances.append(text)
        return True

    def stop(self):
        self.stopped = True
        return True


def pipeline(stt=None, assistant=None, tts=None):
    stt = stt or DummySTT()
    assistant = assistant or DummyAssistant()
    tts = tts or DummyTTS()
    return VoicePipeline(
        assistant, stt, tts=tts,
        settings={"voice": {
            # Only in-memory fake-provider run, never a voice config file.
            "enabled": True, "tts_enabled": True,
            "redundancy_enabled": False,
            "llm_streaming_enabled": False,
            "primary_confidence_threshold": 0.72,
        }},
    ), stt, assistant, tts


def test_synthetic_pcm_complete_stt_assistant_tts_stop(tmp_path):
    p, stt, assistant, tts = pipeline()
    before = list(tmp_path.iterdir())
    result = p.process_utterance(SYNTHETIC_PCM)
    assert result["status"] == "completed"
    assert stt.calls == 1
    assert assistant.messages == [SYNTHETIC_TRANSCRIPT]
    assert tts.utterances == ["Detta är ett syntetiskt svar."]
    assert p.interrupt() is True
    assert tts.stopped is True
    assert p.process_utterance(SYNTHETIC_PCM)["status"] == "clarify"
    assert stt.calls == 1
    assert list(tmp_path.iterdir()) == before


def test_failed_synthetic_stt_must_block_llm_tts_and_private_error():
    p, _, assistant, tts = pipeline(stt=DummySTT(fail=True))
    result = p.process_utterance(SYNTHETIC_PCM)
    assert result["status"] == "clarify"
    assert "PRIVATE_STT_ERROR" not in str(result)
    assert assistant.messages == []
    assert tts.utterances == []


def test_stopped_session_cannot_replay_synthetic_tool_request():
    p, stt, assistant, tts = pipeline()
    p.cancel_pending()
    result = p.process_utterance(SYNTHETIC_PCM)
    assert result["status"] == "clarify"
    assert stt.calls == 0
    assert assistant.messages == []
    assert tts.utterances == []
