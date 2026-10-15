"""Synthetic voice/UI tool execution contract, never runs live tools."""
import pytest

from core.voice_pipeline import VoicePipeline


class FakeSTT:
    def __init__(self, *phrases):
        self.phrases = list(phrases)

    def transcribe(self, audio):
        if not self.phrases:
            raise AssertionError("STT called too many times")
        return {"text": self.phrases.pop(0), "confidence": 0.99}


class ToolStatusAssistant:
    def __init__(self, execution_status=None, tools=None, memory_feedback=None):
        self.execution_status = execution_status
        self.selected_tools = [] if tools is None else tools
        self.memory_feedback = memory_feedback
        self.calls = 0

    def respond(self, text):
        self.calls += 1
        response = {
            "answer": "Resultatet behöver kontrolleras.",
            "tools": self.selected_tools,
            "tool_results": {},
        }
        if self.execution_status is not None:
            response["tool_execution_status"] = self.execution_status
        if self.memory_feedback is not None:
            response["memory_feedback"] = self.memory_feedback
        return response

    def respond_voice(self, text, *, plan_verifier):
        return self.respond(text)


def settings(*, confirm=False):
    return {"voice": {
        "tts_enabled": False,
        "redundancy_enabled": True,
        "redundant_transcript_count": 3,
        "high_risk_confirmation_enabled": confirm,
        "high_risk_confirmation_window_seconds": 20,
    }}


@pytest.mark.parametrize("status,selected,expected", [
    ("completed", ["disk_status"], "completed"),
    ("failed", ["disk_status"], "clarify"),
    ("partially_completed", ["disk_status"], "clarify"),
    ("unknown", ["disk_status"], "clarify"),
    ("not_started", ["disk_status"], "clarify"),
    ("not_applicable", ["disk_status"], "clarify"),
    ("not_started", [], "completed"),
    ("not_applicable", [], "completed"),
    ("completed", [], "completed"),
])
def test_structured_tool_status_controls_ui(status, selected, expected):
    assistant = ToolStatusAssistant(status, tools=selected)
    result = VoicePipeline(
        assistant, FakeSTT("Hur mår systemet"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == expected
    assert result["tool_execution"] == {"status": status}
    assert assistant.calls == 1


def test_legacy_assistant_without_outcomes_cannot_assert_tool_success():
    assistant = ToolStatusAssistant(tools=["read_only_legacy_tool"])
    result = VoicePipeline(
        assistant, FakeSTT("Hur mår systemet"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert "tool_execution" not in result
    assert "kunde inte bekräftas" in result["message"]


def test_legacy_assistant_without_tools_remains_compatible():
    assistant = ToolStatusAssistant(tools=[])
    result = VoicePipeline(
        assistant, FakeSTT("Hur mår systemet"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == "completed"
    assert "tool_execution" not in result


@pytest.mark.parametrize("invalid", [[], {"raw": "SECRET"}, False, "unexpected"])
def test_malformed_tool_status_is_sanitized_and_fails_closed(invalid):
    assistant = ToolStatusAssistant(invalid, tools=["disk_status"])
    result = VoicePipeline(
        assistant, FakeSTT("Hur mår systemet"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["tool_execution"] == {"status": "unknown"}
    assert "SECRET" not in str(result["tool_execution"])


def test_pending_memory_and_failed_tool_both_reflected_without_raw_data():
    assistant = ToolStatusAssistant(
        "failed", tools=["disk_status"],
        memory_feedback={"status": "pending_review", "message": "PRIVATE TEXT"},
    )
    result = VoicePipeline(
        assistant, FakeSTT("Kontrollera systemet"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["memory_feedback"] == {"status": "pending_review"}
    assert result["tool_execution"] == {"status": "failed"}
    assert "PRIVATE TEXT" not in str(result["tool_execution"])
    assert "PRIVATE TEXT" not in str(result["memory_feedback"])


def test_high_risk_confirmation_never_marks_partially_executed_tool_complete():
    assistant = ToolStatusAssistant("partially_completed", tools=["delete_file"])
    pipeline = VoicePipeline(
        assistant,
        FakeSTT("Radera filen rapport", "bekräfta"),
        backup_stt=[
            FakeSTT("Radera filen rapport", "bekräfta"),
            FakeSTT("Radera filen rapport", "bekräfta"),
        ],
        settings=settings(confirm=True),
    )
    before = pipeline.process_utterance(b"synthetic")
    assert before["status"] == "confirmation_required"
    assert assistant.calls == 0
    after = pipeline.process_utterance(b"synthetic")
    assert after["status"] == "clarify"
    assert after["tool_execution"] == {"status": "partially_completed"}
    assert after["confirmation"]["confirmed"] is True
    assert assistant.calls == 1


def test_manual_reconciliation_hint_is_sanitized_for_uncertain_voice_outcome():
    class ReconciliationAssistant(ToolStatusAssistant):
        def respond(self, text):
            result = super().respond(text)
            result["manual_reconciliation_required"] = True
            result["raw_private_arguments"] = "DO_NOT_FORWARD"
            return result

    assistant = ReconciliationAssistant("unknown", tools=["disk_status"])
    result = VoicePipeline(
        assistant, FakeSTT("Kontrollera disken"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["status"] == "clarify"
    assert result["tool_execution"] == {
        "status": "unknown", "manual_reconciliation_required": True,
    }
    assert "DO_NOT_FORWARD" not in str(result["tool_execution"])


def test_manual_reconciliation_hint_never_overrides_a_completed_status():
    class ReconciliationAssistant(ToolStatusAssistant):
        def respond(self, text):
            value = super().respond(text)
            value["manual_reconciliation_required"] = True
            return value

    assistant = ReconciliationAssistant("completed", tools=["disk_status"])
    result = VoicePipeline(
        assistant, FakeSTT("Systemstatus"), settings=settings()
    ).process_utterance(b"synthetic")
    assert result["tool_execution"] == {"status": "completed"}
