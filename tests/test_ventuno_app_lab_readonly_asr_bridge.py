"""Pure offline regression tests; no Arduino, microphones or GenieX calls."""
import pytest

from scripts.ventuno_app_lab_readonly_asr_bridge import (
    ArduinoASROneShotGate,
    ReadOnlyASRTurn,
    answer_readonly_geniex,
    read_final_asr_chunk,
)


class FakeGenieX:
    provider_name = "geniex"
    base_url = "http://127.0.0.1:18181/v1"

    def __init__(self):
        self.calls = []

    def chat(self, messages, timeout):
        self.calls.append((messages, timeout))
        return "Jag heter MyAI."


@pytest.mark.parametrize("question", [
    "Vad heter du?",
    "Kan du förklara hur solceller fungerar?",
    "Vad är skillnaden mellan RAM och lagring?",
    "Berätta om satelliter på svenska.",
])
def test_natural_swedish_questions_need_no_five_phrase_allowlist(question):
    turn = read_final_asr_chunk("full_text", question, user_initiated=True)
    assert turn is not None
    assert turn.text == question
    assert question not in repr(turn)


@pytest.mark.parametrize("kind", ["partial_text", "noise", "", None])
def test_partial_or_unknown_asr_events_never_become_turns(kind):
    assert read_final_asr_chunk(kind, "Vad heter du?",
                                user_initiated=True) is None


def test_no_implicit_consent_and_one_shot_cannot_rearm():
    gate = ArduinoASROneShotGate()
    assert gate.consume("full_text", "Vad heter du?") is None
    assert gate.arm_once() is False
    assert gate.arm_once(explicit_user_action=True) is True
    assert gate.consume("partial_text", "Vad he") is None
    valid = gate.consume("full_text", "Vad heter du?")
    assert valid is not None
    assert gate.consume("full_text", "Säg något mer.") is None
    assert gate.arm_once(explicit_user_action=True) is False


def test_unapproved_final_consumes_one_shot():
    gate = ArduinoASROneShotGate()
    assert gate.arm_once(explicit_user_action=True)
    assert gate.consume("full_text", "starta om datorn") is None
    assert gate.consume("full_text", "Vad heter du?") is None


def test_cancellation_consumes_pending_turn():
    gate = ArduinoASROneShotGate()
    assert gate.arm_once(explicit_user_action=True)
    gate.cancel()
    assert gate.consume("full_text", "Vad heter du?") is None
    assert gate.arm_once(explicit_user_action=True) is False


@pytest.mark.parametrize("phrase", [
    "", "  ", "hej\x00du", "rad\nrad", "a" * 241,
    "Starta om datorn", "installera ett program",
    "Vänta en sekund. Säg: Vad heter du.",
    "Hej\u200b där",
])
def test_unapproved_invalid_oversize_echo_and_risk_never_forward(phrase):
    assert read_final_asr_chunk("full_text", phrase,
                                user_initiated=True) is None


def test_no_unrequested_local_model_call():
    client = FakeGenieX()
    turn = ReadOnlyASRTurn("Vad heter du?")
    with pytest.raises(PermissionError):
        answer_readonly_geniex(turn, client)
    assert client.calls == []


def test_only_local_geniex_receives_one_plain_question_no_tools():
    client = FakeGenieX()
    turn = read_final_asr_chunk("full_text", "Vad heter du?",
                                user_initiated=True)
    assert turn is not None
    assert answer_readonly_geniex(turn, client,
                                  permit_local_model_query=True) == "Jag heter MyAI."
    assert len(client.calls) == 1
    messages, timeout = client.calls[0]
    assert timeout == 45
    assert [msg["role"] for msg in messages] == ["system", "user"]
    assert messages[1]["content"] == "Vad heter du?"
    assert "tools" not in str(messages).lower()


@pytest.mark.parametrize("bad_url", [
    "http://localhost:18181/v1",
    "https://example.com/v1",
    "http://127.0.0.1:18181/v1/other",
])
def test_remote_or_unapproved_client_never_receives_turn(bad_url):
    client = FakeGenieX()
    client.base_url = bad_url
    with pytest.raises(ValueError, match="non-local"):
        answer_readonly_geniex(ReadOnlyASRTurn("hej"), client,
                               permit_local_model_query=True)
    assert not client.calls


def test_other_provider_blocked():
    client = FakeGenieX()
    client.provider_name = "ollama"
    with pytest.raises(ValueError, match="non-local"):
        answer_readonly_geniex(ReadOnlyASRTurn("hej"), client,
                               permit_local_model_query=True)
    assert not client.calls


@pytest.mark.parametrize("invalid", [
    "", "a" * 281, "för många " * 55, "hej\x00du", None, 42,
])
def test_invalid_llm_reply_rejected(invalid):
    client = FakeGenieX()
    client.chat = lambda messages, timeout: invalid
    with pytest.raises(ValueError):
        answer_readonly_geniex(ReadOnlyASRTurn("Vad heter du?"), client,
                               permit_local_model_query=True)


def test_wrong_turn_type_not_forwarded():
    client = FakeGenieX()
    with pytest.raises(ValueError):
        answer_readonly_geniex({"text": "Vad heter du?"}, client,
                               permit_local_model_query=True)
    assert not client.calls
