"""Full VENTUNO voice-session path with exclusively synthetic injected providers.

No microphone, actual STT model, TTS native engine, Geniex connection or NPU.
All components are supplied explicitly, bypassing optional native factories.
"""
from copy import deepcopy
import json

from core.voice_session import VoiceSession
from scripts.ventuno_isolated_voice_stage_contract import SOURCE, candidate


class FakeMicrophone:
    def __init__(self):
        self.data = [b"\x01\x00" * 160, b"\x02\x00" * 160,
                     b"\x00\x00" * 160]
        self.starts = 0
        self.stops = 0
        self.started = False

    def start(self):
        self.starts += 1
        self.started = True
        return True

    def read_frame(self):
        assert self.started
        frame = self.data.pop(0) if self.data else b"\x00\x00" * 160
        return {"frame": frame, "overflowed": False}

    def stop(self):
        self.stops += 1
        self.started = False
        return True


class FakeVAD:
    def __init__(self):
        self.calls = 0

    def is_speech(self, frame):
        self.calls += 1
        return self.calls == 1


class FakeSTT:
    def __init__(self, fail=False):
        self.calls = 0
        self.received = []
        self.fail = fail

    def transcribe(self, audio):
        self.calls += 1
        self.received.append(audio)
        if self.fail:
            raise RuntimeError("PRIVATE_STT_NATIVE_EXCEPTION")
        return {"text": "Vad är klockan?", "confidence": 0.99}


class FakeAssistant:
    def __init__(self):
        self.received = []
        self.llm = None

    def respond(self, text):
        self.received.append(text)
        return {"answer": "Det är ett syntetiskt svar.",
                "tools": [], "tool_results": {}}


class FakeTTS:
    def __init__(self):
        self.spoken = []
        self.stops = 0

    def speak(self, text):
        self.spoken.append(text)
        return True

    def stop(self):
        self.stops += 1
        return True


def _harness(*, fail_stt=False):
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    config = deepcopy(candidate(source))
    assert config["voice"]["enabled"] is False
    assert config["memory"]["auto_save_enabled"] is False
    assert config["files"]["write_enabled"] is False
    assert config["ventuno"]["rpc_write_enabled"] is False
    # Runtime switches change ONLY in this disposable Python dictionary.
    # Real stage JSON stays disabled and NO provider factory is invoked.
    config["voice"]["enabled"] = True
    config["voice"]["tts_enabled"] = True
    config["voice"]["vad_start_speech_frames"] = 1
    config["voice"]["vad_end_silence_frames"] = 2
    config["voice"]["session_max_wait_frames"] = 6
    mic, vad, stt, assistant, tts = (
        FakeMicrophone(), FakeVAD(), FakeSTT(fail_stt),
        FakeAssistant(), FakeTTS()
    )
    session = VoiceSession(
        assistant,
        settings=config,
        components={"enabled": True, "microphone": mic, "vad": vad,
                    "primary_stt": stt, "backup_stt": [], "tts": tts},
    )
    return session, mic, stt, assistant, tts


def test_full_synthetic_microphone_vad_stt_llm_tts_and_stop(tmp_path):
    source_before = SOURCE.read_bytes()
    session, mic, stt, assistant, tts = _harness()
    event = session.run_once(max_wait_frames=6)
    assert event["status"] == "utterance_complete"
    assert event["voice_result"]["status"] == "completed"
    assert assistant.received == ["Vad är klockan?"]
    assert stt.calls == 1
    assert stt.received and b"\x01\x00" in stt.received[0]
    assert tts.spoken == ["Det är ett syntetiskt svar."]
    assert session.stop() is True
    assert not session.running
    assert mic.started is False
    assert mic.stops >= 1
    assert tts.stops >= 1
    assert SOURCE.read_bytes() == source_before
    assert list(tmp_path.iterdir()) == []


def test_failing_synthetic_stt_never_calls_llm_or_speaks():
    session, mic, stt, assistant, tts = _harness(fail_stt=True)
    event = session.run_once(max_wait_frames=6)
    assert event["status"] == "utterance_complete"
    assert event["voice_result"]["status"] == "clarify"
    assert "PRIVATE_STT_NATIVE_EXCEPTION" not in json.dumps(event)
    assert assistant.received == []
    assert tts.spoken == []
    session.stop()
    assert mic.started is False


def test_staged_actual_file_is_disabled_before_and_after_synthetic_session():
    from scripts.ventuno_isolated_voice_stage_contract import inspect
    before = inspect()
    assert before["candidate_safe_by_contract"]
    session, *_ = _harness()
    session.run_once(max_wait_frames=6)
    session.stop()
    assert inspect() == before
