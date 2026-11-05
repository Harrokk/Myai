"""Synthetic Arduino ASREvent/TranscriptionStream compatibility contract."""
from dataclasses import dataclass

import pytest

from integrations.arduino_app_lab.asr_v2.boundary import FinalTextOneShotGate
from integrations.arduino_app_lab.asr_v2.sdk_events import (
    MAX_SDK_EVENTS, check_official_brick_contract,
    consume_official_asr_stream,
)


@dataclass(frozen=True)
class FakeASREvent:
    type: str
    data: object


class FakeSDKStream:
    def __init__(self, events, *, fail_exit=False):
        self.events = events
        self.entered = 0
        self.exited = 0
        self.fail_exit = fail_exit

    def __enter__(self):
        self.entered += 1
        return iter(self.events)

    def __exit__(self, exc_type, exc, tb):
        self.exited += 1
        if self.fail_exit:
            raise RuntimeError("PRIVATE_SDK_TRANSCRIPT_SHOULD_NOT_LEAK")
        return False


class FakeBrick:
    language = "sv"
    translate = False

    def transcribe_sentence_stream(self, *, timeout=0):
        raise AssertionError("MUST NOT OPEN MICROPHONE IN CONTRACT TEST")

    def cancel(self):
        raise AssertionError("MUST NOT CANCEL REAL BRICK IN CONTRACT TEST")

    def stop(self):
        raise AssertionError("MUST NOT STOP REAL BRICK IN CONTRACT TEST")


def armed():
    gate = FinalTextOneShotGate()
    assert gate.arm_once(explicit_ui_action=True)
    return gate


def test_official_brick_metadata_no_sdk_methods_are_called():
    assert check_official_brick_contract(FakeBrick())
    fake = FakeBrick()
    fake.translate = True
    assert not check_official_brick_contract(fake)
    fake.translate = False
    fake.language = "en"
    assert not check_official_brick_contract(fake)


@pytest.mark.parametrize("obj", [None, object(), 1, {}, "sv"])
def test_unknown_asr_brick_is_not_accepted(obj):
    assert check_official_brick_contract(obj) is False


def test_official_full_text_is_consumed_without_partial_text_read():
    class Partial:
        type = "partial_text"

        @property
        def data(self):
            raise AssertionError("NEVER_INSPECT_PRIVATE_PARTIAL_TEXT")

    events = FakeSDKStream([
        Partial(),
        FakeASREvent("partial_text", "superhemligt"),
        FakeASREvent("full_text", "  Vad heter du?  "),
        FakeASREvent("full_text", "second private phrase"),
    ])
    gate = armed()
    report = consume_official_asr_stream(events, gate)
    assert report.status == "final-ready"
    assert report.events_seen == 3
    assert report.final_text.text == "Vad heter du?"
    assert events.entered == events.exited == 1
    assert "Vad" not in repr(report)
    assert gate.consume("full_text", "another phrase") is None
    assert gate.arm_once(explicit_ui_action=True) is False


def test_first_bad_full_text_cannot_be_retried():
    events = FakeSDKStream([
        FakeASREvent("full_text", "hemligt\x00"),
        FakeASREvent("full_text", "Vad heter du?"),
    ])
    result = consume_official_asr_stream(events, armed())
    assert result.status == "final-rejected"
    assert result.events_seen == 1
    assert result.final_text is None
    assert events.exited == 1


def test_only_partial_events_are_not_a_transcript():
    s = FakeSDKStream([FakeASREvent("partial_text", "secret")])
    r = consume_official_asr_stream(s, armed())
    assert r.status == "no-final"
    assert r.final_text is None
    assert s.exited == 1


def test_unrecognized_event_fails_closed_without_exposing_words():
    s = FakeSDKStream([
        FakeASREvent("forced_tool_command", "SECRET_DELETE_ALL"),
        FakeASREvent("full_text", "Vad heter du?"),
    ])
    result = consume_official_asr_stream(s, armed())
    assert result.status == "unexpected-asr-event"
    assert result.final_text is None
    assert "SECRET" not in repr(result)


def test_bounded_stream_rejects_unending_partials_and_closes():
    s = FakeSDKStream(
        [FakeASREvent("partial_text", "SECRET")] * (MAX_SDK_EVENTS + 5)
    )
    report = consume_official_asr_stream(s, armed())
    assert report.status == "event-budget-exceeded"
    assert report.events_seen == MAX_SDK_EVENTS
    assert report.final_text is None
    assert s.exited == 1


def test_stream_exception_never_exposes_private_data():
    def crashing_events():
        yield FakeASREvent("partial_text", "private")
        raise RuntimeError("THE_REAL_RECOGNIZED_WORDS")

    s = FakeSDKStream(crashing_events())
    r = consume_official_asr_stream(s, armed())
    assert r.status == "stream-failed"
    assert r.final_text is None
    assert s.exited == 1
    assert "REAL" not in repr(r)


def test_context_exit_failure_revokes_successful_final():
    s = FakeSDKStream(
        [FakeASREvent("full_text", "Vad heter du?")],
        fail_exit=True,
    )
    r = consume_official_asr_stream(s, armed())
    assert r.status == "stream-failed"
    assert r.final_text is None
    assert s.exited == 1


def test_unarmed_gate_returns_no_final_and_cannot_retry():
    gate = FinalTextOneShotGate()
    stream = FakeSDKStream([FakeASREvent("full_text", "Vad heter du?")])
    result = consume_official_asr_stream(stream, gate)
    assert result.status == "final-rejected"
    assert result.final_text is None
    assert gate.arm_once(explicit_ui_action=True) is False


def test_invalid_gate_never_opens_stream():
    stream = FakeSDKStream([FakeASREvent("full_text", "Vad heter du?")])
    result = consume_official_asr_stream(stream, None)
    assert result.status == "invalid-one-shot-gate"
    assert stream.entered == 0
