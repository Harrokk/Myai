"""Synthetic streaming speech gate for tool outcomes, never touches hardware."""
import pytest

from core.voice_pipeline import VoicePipeline


class FakeSTT:
    def __init__(self, text):
        self.text = text
    def transcribe(self, audio):
        return {"text": self.text, "confidence": 0.99}


class FakeTTS:
    def __init__(self):
        self.spoken = []
    def speak(self, value):
        self.spoken.append(value)
    def stop(self):
        return True


class StreamingToolAssistant:
    def __init__(self, status="failed", *, has_tool=True, effect="read_only"):
        self.status = status
        self.has_tool = has_tool
        self.effect = effect
        self.pipeline = None
        self.observed_enqueue_before_finish = []
        self.tools = (
            {"disk_status": {
                "function": lambda: "fake",
                "safety": {
                    "effect": effect,
                    "voice_confirmation_required": effect != "read_only",
                },
            }}
            if has_tool else {}
        )

    def preview_tool_plan(self, command):
        return {
            "steps": (
                [{"tool": "disk_status", "input": command}]
                if self.has_tool else []
            )
        }

    def respond_stream(self, text, on_chunk=None):
        # Presence makes stream dispatch enabled; real call uses
        # respond_voice_stream, which requires a verifier callback.
        return self.respond_voice_stream(text, on_chunk=on_chunk, plan_verifier=lambda *_: True)

    def respond_voice_stream(self, text, *, on_chunk, plan_verifier):
        for chunk in ["Falskt påstående: ", "verktyget lyckades."]:
            on_chunk(chunk)
            self.observed_enqueue_before_finish.append(
                self.pipeline.streaming_tts.started_at is not None
            )
        return {
            "answer": "Falskt påstående: verktyget lyckades.",
            "tools": ["disk_status"] if self.has_tool else [],
            "tool_results": {},
            "tool_execution_status": self.status,
            "streamed": True,
        }

    def respond(self, text):
        raise AssertionError("Expected guarded streaming path")


def settings(confirm=False):
    return {"voice": {
        "tts_enabled": True,
        "llm_streaming_enabled": True,
        "stream_tts_min_chars": 5,
        "stream_tts_max_chars": 200,
        "redundancy_enabled": True,
        "redundant_transcript_count": 3,
        "high_risk_confirmation_enabled": confirm,
        "high_risk_confirmation_window_seconds": 15,
    }}


@pytest.mark.parametrize("status", [
    "failed", "partially_completed", "unknown", "not_started", "not_applicable",
])
def test_stream_tool_status_must_arrive_before_any_speech(status):
    assistant = StreamingToolAssistant(status=status)
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Visa diskinformation"),
        tts=tts, settings=settings(),
    )
    assistant.pipeline = pipeline
    result = pipeline.process_utterance(b"fake-audio")
    assert assistant.observed_enqueue_before_finish == [False, False]
    assert result["status"] == "clarify"
    assert result["tool_execution"]["status"] == status
    assert "Falskt påstående" not in result["message"]
    assert result["assistant"]["answer"] == result["message"]
    assert pipeline.streaming_tts.wait(timeout=2)
    assert tts.spoken
    assert "Falskt påstående" not in " ".join(tts.spoken)


def test_successful_tool_stream_waits_for_result_then_speaks_original_answer():
    assistant = StreamingToolAssistant(status="completed")
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Visa diskinformation"),
        tts=tts, settings=settings(),
    )
    assistant.pipeline = pipeline
    result = pipeline.process_utterance(b"fake-audio")
    assert assistant.observed_enqueue_before_finish == [False, False]
    assert result["status"] == "completed"
    assert pipeline.streaming_tts.wait(timeout=2)
    assert " ".join(tts.spoken) == "Falskt påstående: verktyget lyckades."


def test_verified_tool_free_dialogue_is_streamed_before_completion():
    assistant = StreamingToolAssistant(status="not_applicable", has_tool=False)
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Berätta något"),
        tts=tts, settings=settings(),
    )
    assistant.pipeline = pipeline
    result = pipeline.process_utterance(b"fake-audio")
    assert result["status"] == "completed"
    assert assistant.observed_enqueue_before_finish[-1] is True
    assert pipeline.streaming_tts.wait(timeout=2)
    assert tts.spoken == ["Falskt påstående: verktyget lyckades."]


def test_high_risk_confirmation_speech_is_not_early_success():
    assistant = StreamingToolAssistant("partially_completed", effect="write")
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Radera filen rapport"),
        backup_stt=[
            FakeSTT("Radera filen rapport"),
            FakeSTT("Radera filen rapport"),
        ], tts=tts, settings=settings(confirm=True),
    )
    assistant.pipeline = pipeline
    start = pipeline.process_utterance(b"fake-audio")
    assert start["status"] == "confirmation_required"
    tts.spoken.clear()
    pipeline.primary_stt.text = "bekräfta"
    for backup in pipeline.backup_stt:
        backup.text = "bekräfta"
    confirmed = pipeline.process_utterance(b"fake-audio")
    assert confirmed["status"] == "clarify"
    assert confirmed["confirmation"]["confirmed"] is True
    assert confirmed["tool_execution"] == {"status": "partially_completed"}
    assert assistant.observed_enqueue_before_finish == [False, False]
    assert pipeline.streaming_tts.wait(timeout=2)
    assert "Falskt påstående" not in " ".join(tts.spoken)
    assert "Tidigare ändringar kan finnas kvar" in " ".join(tts.spoken)


def test_legacy_no_plan_stream_is_deferred_and_not_announced_as_success():
    class LegacyToolAssistant:
        def __init__(self):
            self.pipeline = None
        def respond_stream(self, text, on_chunk=None):
            on_chunk("Det är genomfört.")
            assert self.pipeline.streaming_tts.started_at is None
            return {
                "answer": "Det är genomfört.",
                "tools": ["workspace_write"],
                "tool_execution_status": "failed",
                "tool_results": {},
            }
    assistant = LegacyToolAssistant()
    tts = FakeTTS()
    pipeline = VoicePipeline(
        assistant, FakeSTT("Visa information"), tts=tts,
        settings=settings(),
    )
    assistant.pipeline = pipeline
    result = pipeline.process_utterance(b"fake")
    assert result["status"] == "clarify"
    assert pipeline.streaming_tts.wait(timeout=2)
    assert "Det är genomfört" not in " ".join(tts.spoken)
