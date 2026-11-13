"""Fake-peer complete App Lab Alma -> MyAI -> Alma response contract tests.

Uses the real source-only protocol modules when run in the MyAI repository.
No physical socket is created, no backend, model, audio or memory database used.
"""
import socket
import struct
from types import SimpleNamespace

import pytest

from core.app_lab_unix_final_text import (
    OneSessionReplayGuard, run_authenticated_final_turn,
)
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from integrations.arduino_app_lab.alma_reference.source_contract import (
    AlmaFinalASRGate, sign_final_for_myai,
)
from integrations.arduino_app_lab.alma_reference.private_reply import (
    OneSessionReplyGuard, frame_signed_reply, make_signed_reply,
    unframe_signed_reply, verify_signed_reply,
)

SESSION = "1" * 32
REQUEST = "2" * 32
SECRET = b"p" * 32  # Test fixture only; no runtime secret or key generation.
NOW = 1900000000


class FakeUnixPeer:
    family = socket.AF_UNIX

    def __init__(self, payload, *, uid=1001):
        self.data = bytearray(struct.pack("!I", len(payload)) + payload)
        self.uid = uid

    def getsockopt(self, level, optname, length):
        return struct.pack("3i", 456, self.uid, 100)

    def gettimeout(self):
        return 0.2

    def recv(self, size):
        result = bytes(self.data[:size])
        del self.data[:size]
        return result


class FakeMyAI:
    settings = {"memory": {
        "auto_assess_enabled": False,
        "auto_save_enabled": False,
        "review_queue_enabled": False,
        "lifecycle_enabled": False,
    }}

    def __init__(self, response=None, stop_on_response=None):
        self.calls = []
        self.response = response if response is not None else {
            "answer": "Solceller gör ljus till el.",
            "tool_execution_status": "not_applicable",
            "manual_reconciliation_required": False,
            "tool_dispatch_blocked": False,
        }
        self.stop_on_response = stop_on_response

    def respond_voice(self, text, *, plan_verifier):
        self.calls.append(text)
        # A receiver never inherits voice approval for a write command.
        assert plan_verifier({"steps": [{"tool": "delete"}]}, {}) is False
        if self.stop_on_response is not None:
            self.stop_on_response[0] = True
        return self.response


def from_stream(*events, stopped=None):
    stopped = stopped if stopped is not None else [False]
    gate = AlmaFinalASRGate()
    for kind, value in events:
        gate.feed(SimpleNamespace(type=kind, data=value))
    return gate.take_final(
        session_active=True, asr_released=True,
        stop_requested=lambda: stopped[0],
    )


def through_myai(text, core=None, stopped=None, *, request_secret=SECRET):
    stopped = stopped if stopped is not None else [False]
    core = core or FakeMyAI()
    req = sign_final_for_myai(
        text, secret=request_secret, session_id=SESSION,
        request_id=REQUEST, issued_at=NOW,
    )
    outcome = run_authenticated_final_turn(
        FakeUnixPeer(req), expected_uid=1001, secret=SECRET,
        active_session=SESSION, replay_guard=OneSessionReplayGuard(session_id=SESSION),
        handoff=AppLabFinalTextHandoff(core, enabled=True),
        session_active=lambda: True, asr_released=lambda: True,
        stop_requested=lambda: stopped[0], enabled=True, clock=lambda: NOW,
    )
    return outcome, core


def verified_return(outcome, *, stopped=None):
    stopped = stopped if stopped is not None else [False]
    signed = make_signed_reply(
        result=outcome, secret=SECRET, session_id=SESSION,
        request_id=REQUEST, issued_at=NOW + 1,
    )
    # This represents bytes only. There is no live connection or speaker.
    framed = frame_signed_reply(signed)
    reply = verify_signed_reply(
        unframe_signed_reply(framed), secret=SECRET,
        active_session=SESSION, expected_request=REQUEST, now=NOW + 1,
        replay_guard=OneSessionReplyGuard(session_id=SESSION),
        stop_requested=lambda: stopped[0],
    )
    return reply, signed


def test_complete_private_turn_only_final_is_readied_for_alma():
    final = from_stream(("partial_text", "Hur fungerar"),
                        ("full_text", "Hur fungerar solceller?"))
    assert final == "Hur fungerar solceller?"
    outcome, core = through_myai(final)
    assert outcome["status"] == "answer-ready"
    assert core.calls == ["Hur fungerar solceller?"]
    reply, signed = verified_return(outcome)
    assert reply == {"status": "ready", "answer": "Solceller gör ljus till el."}
    assert "Hur fungerar solceller?" not in signed.decode("utf-8")


def test_partial_asr_fallback_is_not_eligible_to_invoke_myai():
    assert from_stream(("partial_text", "Ta bort allt")) is None
    with pytest.raises(ValueError):
        sign_final_for_myai(None, secret=SECRET, session_id=SESSION,
                            request_id=REQUEST, issued_at=NOW)


def test_blocked_core_cannot_leak_answer_in_tts_return():
    core = FakeMyAI(response={
        "answer": "Skriv över hemlig fil", "tool_execution_status": "blocked",
        "tool_dispatch_blocked": True, "manual_reconciliation_required": False,
    })
    outcome, _ = through_myai("Gör ändringen", core=core)
    assert outcome["status"] == "tool-dispatch-blocked"
    reply, signed = verified_return(outcome)
    assert reply == {"status": "withheld"}
    assert "hemlig fil" not in signed.decode("utf-8")


def test_unknown_outcome_requires_review_and_withholds_spoken_answer():
    core = FakeMyAI(response={
        "answer": "PRIVATE MODEL OUTPUT", "tool_execution_status": "unknown",
        "tool_dispatch_blocked": False, "manual_reconciliation_required": True,
    })
    outcome, _ = through_myai("Kontrollera", core=core)
    assert outcome["status"] == "review-required"
    reply, signed = verified_return(outcome)
    assert reply == {"status": "withheld"}
    assert "PRIVATE MODEL OUTPUT" not in signed.decode("utf-8")


def test_stop_during_core_prevents_answer_reaching_alma():
    stop = [False]
    core = FakeMyAI(stop_on_response=stop)
    outcome, _ = through_myai("Vad händer?", core=core, stopped=stop)
    assert outcome == {"status": "cancelled"}
    with pytest.raises(ValueError):
        verified_return(outcome, stopped=stop)


def test_wrong_request_identity_prevents_playback():
    outcome, _ = through_myai("Hur fungerar det?")
    signed = make_signed_reply(result=outcome, secret=SECRET,
                               session_id=SESSION, request_id=REQUEST,
                               issued_at=NOW + 1)
    with pytest.raises(ValueError):
        verify_signed_reply(
            signed, secret=SECRET, active_session=SESSION,
            expected_request="f" * 32, now=NOW + 1,
            replay_guard=OneSessionReplyGuard(session_id=SESSION),
            stop_requested=lambda: False,
        )


def test_no_auto_memory_policy_on_untrusted_host():
    class UnsafeCore(FakeMyAI):
        settings = {"memory": {"auto_save_enabled": True}}
    outcome, core = through_myai("Hej", core=UnsafeCore())
    assert outcome == {"status": "memory-policy-unsafe"}
    assert core.calls == []
