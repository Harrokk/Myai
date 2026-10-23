"""Strict mock-only contracts for the official Arduino Brick streaming interface."""
from dataclasses import dataclass
from types import SimpleNamespace

import pytest

from scripts.ventuno_app_lab_one_turn import (
    ArduinoBrickOneTurn, CAPTURE_SECONDS, RELEASE_PAUSE_SECONDS,
)


@dataclass
class FakeStream:
    events: list
    audit: list

    def __enter__(self):
        self.audit.append("enter")
        return iter(self.events)

    def __exit__(self, exc_type, exc, traceback):
        self.audit.append("exit")


class FakeASR:
    def __init__(self, events=(), *, audit=None, stop_fails=False):
        self.events = events
        self.audit = audit if audit is not None else []
        self.stop_fails = stop_fails

    def transcribe_stream(self, *, duration):
        assert duration == CAPTURE_SECONDS == 5
        self.audit.append("capture")
        return FakeStream(list(self.events), self.audit)

    def stop(self):
        self.audit.append("stop")
        if self.stop_fails:
            raise RuntimeError("private failure")


class FakeLocal:
    provider_name = "geniex"
    base_url = "http://127.0.0.1:18181/v1"

    def __init__(self, audit):
        self.audit = audit

    def chat(self, messages, timeout):
        self.audit.append("model")
        assert messages[1]["content"] == "Hur fungerar solceller?"
        return "Solceller gör ljus till el."


def event(kind, data):
    return SimpleNamespace(type=kind, data=data)


def test_import_or_unapproved_call_never_opens_mic():
    audit = []
    turn = ArduinoBrickOneTurn()
    result = turn.run_once(FakeASR([event("full_text", "hej")], audit=audit))
    assert result.status == "not-authorized-or-used"
    assert audit == []


def test_one_explicit_asr_turn_ignores_partials_and_releases_before_any_output():
    audit = []
    seen = []
    asr = FakeASR([
        event("partial_text", "Hur fun"),
        event("partial_text", "Hur fungerar"),
        event("full_text", "Hur fungerar solceller?"),
        event("full_text", "Får inte användas"),
    ], audit=audit)
    pilot = ArduinoBrickOneTurn()
    result = pilot.run_once(
        asr, explicit_user_action=True,
        private_final_handler=lambda text: seen.append(text),
    )
    assert result.status == "final-ready-no-model-call"
    assert result.final_accepted is True and result.model_called is False
    assert seen == ["Hur fungerar solceller?"]
    assert audit == ["capture", "enter", "exit", "stop"]
    assert pilot.run_once(asr, explicit_user_action=True).status == "not-authorized-or-used"


def test_one_local_geniex_call_occurs_after_asr_close_and_1_5_second_release():
    audit = []
    def pause(seconds):
        assert seconds == RELEASE_PAUSE_SECONDS == 1.5
        audit.append("pause")
    asr = FakeASR([
        event("partial_text", "Hur fungerar"),
        event("full_text", "Hur fungerar solceller?"),
    ], audit=audit)
    result = ArduinoBrickOneTurn().run_once(
        asr, explicit_user_action=True,
        local_model_client=FakeLocal(audit),
        permit_local_model_query=True,
        release_pause=pause,
    )
    assert result.status == "local-readonly-answer-completed"
    assert result.model_called is True
    assert audit == ["capture", "enter", "exit", "stop", "pause", "model"]


def test_model_query_cannot_proceed_without_client_or_release_callback():
    for client, pause in ((None, lambda _: None), (object(), None)):
        audit = []
        pilot = ArduinoBrickOneTurn()
        result = pilot.run_once(
            FakeASR(audit=audit), explicit_user_action=True,
            local_model_client=client, permit_local_model_query=True,
            release_pause=pause,
        )
        assert result.status == "model-handoff-not-configured"
        assert audit == []
        assert pilot.run_once(FakeASR(), explicit_user_action=True).status == "not-authorized-or-used"


@pytest.mark.parametrize("events", [
    [], [event("partial_text", "Vad heter")],
    [event("full_text", "starta om datorn")],
    [event("full_text", "Vänta en sekund. Säg: Vad heter du.")],
    [event("full_text", "a" * 241)],
])
def test_no_approved_final_never_queries_model(events):
    audit = []
    res = ArduinoBrickOneTurn().run_once(
        FakeASR(events, audit=audit), explicit_user_action=True,
        local_model_client=FakeLocal(audit),
        permit_local_model_query=True,
        release_pause=lambda _: audit.append("pause"),
    )
    assert res.status == "no-approved-final"
    assert res.model_called is False
    assert audit == ["capture", "enter", "exit", "stop"]


def test_invalid_asr_port_consumes_one_shot():
    pilot = ArduinoBrickOneTurn()
    first = pilot.run_once(object(), explicit_user_action=True)
    assert first.status == "invalid-asr-brick"
    assert not first.capture_attempted
    assert pilot.run_once(FakeASR(), explicit_user_action=True).status == "not-authorized-or-used"


def test_release_failure_never_calls_model():
    audit = []
    res = ArduinoBrickOneTurn().run_once(
        FakeASR([event("full_text", "Hur fungerar solceller?")],
                audit=audit, stop_fails=True),
        explicit_user_action=True,
        local_model_client=FakeLocal(audit),
        permit_local_model_query=True,
        release_pause=lambda _: audit.append("pause"),
    )
    assert res.status == "asr-release-failed"
    assert "model" not in audit and "pause" not in audit


def test_error_does_not_echo_transcript_or_model_words():
    class FaultASR(FakeASR):
        def transcribe_stream(self, *, duration):
            raise RuntimeError("SECRET SPOKEN DATA")
    result = ArduinoBrickOneTurn().run_once(FaultASR(), explicit_user_action=True)
    assert result.status == "asr-failed"
    assert "SECRET" not in repr(result)


def test_private_output_failure_disallows_model_call():
    audit = []
    def bad_sink(text):
        raise RuntimeError("private output failure")
    res = ArduinoBrickOneTurn().run_once(
        FakeASR([event("full_text", "Hur fungerar solceller?")],
                audit=audit),
        explicit_user_action=True,
        private_final_handler=bad_sink,
        local_model_client=FakeLocal(audit),
        permit_local_model_query=True,
        release_pause=lambda _: audit.append("pause"),
    )
    assert res.status == "private-output-failed"
    assert "model" not in audit


def test_bad_non_local_client_never_receives_words():
    audit = []
    client = FakeLocal(audit)
    client.base_url = "http://example.com:18181/v1"
    res = ArduinoBrickOneTurn().run_once(
        FakeASR([event("full_text", "Hur fungerar solceller?")], audit=audit),
        explicit_user_action=True,
        local_model_client=client,
        permit_local_model_query=True,
        release_pause=lambda _: audit.append("pause"),
    )
    assert res.status == "local-answer-blocked"
    assert "model" not in audit
