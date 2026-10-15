"""Offline voice-to-UI memory status contracts, no mic, model or real data."""
from copy import deepcopy
import sqlite3

import pytest

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.memory import MemoryStore
from core.voice_pipeline import VoicePipeline


class FakeSTT:
    def __init__(self, transcript):
        self.transcript = transcript
    def transcribe(self, audio):
        return {"text": self.transcript, "confidence": 0.99}


class FakeTTS:
    def __init__(self):
        self.spoken = []
    def speak(self, text):
        self.spoken.append(text)
    def stop(self):
        return True


class StubMemoryAssistant:
    def __init__(self, state):
        self.state = state
        self.calls = 0

    def respond(self, text):
        self.calls += 1
        return {
            "answer": "Säkert fast meddelande utan rådata.",
            "tools": [],
            "tool_results": {},
            "memory_feedback": {"status": self.state, "message": "DOLD DATA"},
        }

    def respond_voice(self, text, *, plan_verifier):
        return self.respond(text)

    def respond_stream(self, text, on_chunk):
        result = self.respond(text)
        on_chunk(result["answer"])
        return {**result, "streamed": True}

    def respond_voice_stream(self, text, *, plan_verifier, on_chunk):
        return self.respond_stream(text, on_chunk)


def voice_config(*, stream=False, confirmation=False):
    return {"voice": {
        "tts_enabled": True,
        "llm_streaming_enabled": stream,
        "stream_tts_min_chars": 5,
        "stream_tts_max_chars": 150,
        "redundancy_enabled": True,
        "redundant_transcript_count": 3,
        "high_risk_confirmation_enabled": confirmation,
        "high_risk_confirmation_window_seconds": 15,
        "high_risk_confirmation_min_confidence": 0.8,
    }}


@pytest.mark.parametrize("state", [
    "retry_required",
    "not_saved",
    "pending_review",
    "not_saved_sensitive",
    "unverified",
])
def test_memory_not_persisted_voice_ui_is_not_completed(state):
    assistant = StubMemoryAssistant(state)
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Kom ihåg detta"),
        tts=tts, settings=voice_config(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert result["memory_feedback"] == {"status": state}
    assert result["message"] == result["assistant"]["answer"]
    assert "DOLD DATA" not in str(result["memory_feedback"])
    assert tts.spoken == [result["message"]]
    assert assistant.calls == 1


@pytest.mark.parametrize("state", ["saved", "already_present", "not_requested"])
def test_successful_or_unrelated_memory_keeps_completed_voice_status(state):
    assistant = StubMemoryAssistant(state)
    pipeline = VoicePipeline(
        assistant, FakeSTT("Fråga om projektet"),
        settings=voice_config(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "completed"
    assert result["memory_feedback"] == {"status": state}


def test_old_assistants_without_memory_feedback_remain_compatible():
    class OldAssistant:
        def respond(self, text):
            return {"answer": "Hej", "tools": [], "tool_results": {}}
    pipeline = VoicePipeline(
        OldAssistant(), FakeSTT("Hej"), settings=voice_config(),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "completed"
    assert "memory_feedback" not in result


def test_unrecognized_feedback_state_cannot_claim_success():
    assistant = StubMemoryAssistant("unknown_external_state")
    result = VoicePipeline(
        assistant, FakeSTT("Kom ihåg"), settings=voice_config(),
    ).process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert result["memory_feedback"] == {"status": "unverified"}


def test_streamed_tts_uses_only_final_memory_notice():
    assistant = StubMemoryAssistant("retry_required")
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Kom ihåg instruktionen"),
        tts=tts, settings=voice_config(stream=True),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert result["memory_feedback"]["status"] == "retry_required"
    assert pipeline.streaming_tts is not None
    assert pipeline.streaming_tts.wait(timeout=2) is True
    assert "".join(tts.spoken) == result["assistant"]["answer"]
    assert "DOLD DATA" not in "".join(tts.spoken)


class FaultMemory(MemoryStore):
    def __init__(self, path):
        super().__init__(path)
        self.outage = False
        self.write_count = 0

    def search(self, text):
        if self.outage:
            raise sqlite3.OperationalError("PRIVATE_REAL_LOCATION")
        return super().search(text)

    def save_if_new(self, category, content):
        self.write_count += 1
        return super().save_if_new(category, content)


class MockLLM:
    def chat(self, *args, **kwargs):
        return "Jag har sparat det."
    def chat_stream(self, *args, **kwargs):
        yield "Jag har "
        yield "sparat det."


def make_real_core(tmp_path, monkeypatch):
    import core.assistant as assistant_module
    conf = deepcopy(DEFAULT_SETTINGS)
    conf["memory"]["auto_assess_enabled"] = True
    store = FaultMemory(tmp_path / "synthetic-memory.db")
    store.init()
    core = MyAICore(conf, tmp_path, tools={}, memory=store, llm=MockLLM())
    monkeypatch.setattr(
        assistant_module, "select_tool_plan",
        lambda *_args, **_kwargs: {"steps": [], "source": "synthetic"},
    )
    return core, store


def test_real_core_to_voice_pipeline_reports_sqlite_outage(tmp_path, monkeypatch):
    core, store = make_real_core(tmp_path, monkeypatch)
    store.outage = True
    phrase = "Kom ihåg att jag föredrar modulär kod."
    pipeline = VoicePipeline(
        core, FakeSTT(phrase), settings=voice_config(),
    )
    answer = pipeline.process_utterance(b"synthetic-audio")
    assert answer["status"] == "clarify"
    assert answer["memory_feedback"]["status"] == "retry_required"
    assert answer["assistant"]["memory_lookup_status"] == "unavailable"
    assert "Minnet sparades inte" in answer["message"]
    assert "PRIVATE_REAL_LOCATION" not in str(answer)
    assert store.write_count == 0


def test_real_core_voice_recovery_then_duplicate_is_not_resaved(
        tmp_path, monkeypatch):
    core, store = make_real_core(tmp_path, monkeypatch)
    store.outage = True
    phrase = "Kom ihåg att jag föredrar modulär kod."
    pipeline = VoicePipeline(
        core, FakeSTT(phrase), settings=voice_config(),
    )
    assert pipeline.process_utterance(b"fake")["status"] == "clarify"
    store.outage = False
    first = pipeline.process_utterance(b"fake")
    assert first["status"] == "completed"
    assert first["memory_feedback"]["status"] == "saved"
    again = pipeline.process_utterance(b"fake")
    assert again["status"] == "completed"
    assert again["memory_feedback"]["status"] == "already_present"
    assert len(store.get_all()) == 1
    assert store.write_count == 1


def test_real_core_streamed_memory_outage_reports_clarify_and_no_false_tts(
        tmp_path, monkeypatch):
    core, store = make_real_core(tmp_path, monkeypatch)
    store.outage = True
    tts = FakeTTS()
    pipeline = VoicePipeline(
        core,
        FakeSTT("Kom ihåg att jag föredrar modulär kod."),
        tts=tts,
        settings=voice_config(stream=True),
    )
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert result["memory_feedback"]["status"] == "retry_required"
    assert pipeline.streaming_tts.wait(timeout=2)
    assert "Jag har sparat" not in " ".join(tts.spoken)
    assert "Minnet sparades inte" in " ".join(tts.spoken)
    assert len(tts.spoken) >= 1
