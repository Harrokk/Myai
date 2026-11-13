"""Synthetic Unix final-text bridge tests; never bind, record or deploy."""
import json
import os
import socket
import struct
from concurrent.futures import ThreadPoolExecutor

import pytest

from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from core.app_lab_unix_final_text import (
    MAX_FRAME_BYTES, MAX_WALL_AGE_SECONDS, OneSessionReplayGuard,
    make_signed_request, read_connected_frame,
    run_authenticated_final_turn, verify_signed_request,
)

KEY = b"m" * 32                 # TEST-ONLY; never use in runtime
WRONG_KEY = b"w" * 32
SESSION = "a" * 32
OTHER_SESSION = "b" * 32
RID = "c" * 32
NOW = 1800000000


class FakeCore:
    def __init__(self):
        self.calls = []

    def respond_voice(self, text, *, plan_verifier):
        self.calls.append((text, plan_verifier))
        return {
            "answer": "MyAI läste den svenska frågan.",
            "tool_execution_status": "not_applicable",
            "tool_dispatch_blocked": False,
            "manual_reconciliation_required": False,
        }


def message(**patch):
    config = {
        "secret": KEY, "session_id": SESSION, "request_id": RID,
        "issued_at": NOW, "text": "Vad heter du?",
    }
    config.update(patch)
    return make_signed_request(**config)


def test_valid_hmac_roundtrip():
    parsed = verify_signed_request(
        message(), secret=KEY, active_session=SESSION, now=NOW,
    )
    assert parsed["text"] == "Vad heter du?"
    assert parsed["request_id"] == RID
    assert "mac" not in parsed


@pytest.mark.parametrize("patch", [
    {"secret": WRONG_KEY},
    {"session_id": OTHER_SESSION},
    {"issued_at": NOW - MAX_WALL_AGE_SECONDS - 1},
    {"issued_at": NOW + 3},
])
def test_wrong_key_session_or_time_rejected(patch):
    raw = message(**patch)
    with pytest.raises(ValueError):
        verify_signed_request(
            raw, secret=KEY, active_session=SESSION, now=NOW,
        )


def test_tampered_text_is_rejected_even_if_valid_json():
    data = json.loads(message())
    data["text"] = "stäng av datorn"
    raw = json.dumps(data).encode()
    with pytest.raises(ValueError):
        verify_signed_request(
            raw, secret=KEY, active_session=SESSION, now=NOW,
        )


@pytest.mark.parametrize("bad", [
    b"", b"{}", b"invalid", b"\xff", b"[]" + b" " * 10,
    b'{"version":1,"version":1}', b'{"x":NaN}',
])
def test_malformed_rejected(bad):
    with pytest.raises(ValueError):
        verify_signed_request(bad, secret=KEY, active_session=SESSION, now=NOW)


@pytest.mark.parametrize("text", [
    "", "  ", "a" * 501, "x\x00private", "a\nb",
    "Hej\u202e", "\ud800",
])
def test_malicious_or_invalid_text_never_signed(text):
    with pytest.raises((ValueError, UnicodeError)):
        message(text=text)


def test_extra_claims_and_duplicate_fields_rejected():
    raw = message()
    record = json.loads(raw)
    record["asr_released"] = True
    with pytest.raises(ValueError):
        verify_signed_request(
            json.dumps(record).encode(), secret=KEY,
            active_session=SESSION, now=NOW,
        )
    original = raw.decode()
    duplicate = original.replace('"action":', '"action":"submit_final","action":', 1)
    with pytest.raises(ValueError):
        verify_signed_request(
            duplicate.encode(), secret=KEY, active_session=SESSION, now=NOW,
        )


def test_replay_capacity_strict_and_thread_safe():
    guard = OneSessionReplayGuard(session_id=SESSION, max_requests=1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        accepted = list(pool.map(
            lambda _: guard.accept_once(SESSION, RID), range(16)
        ))
    assert sum(accepted) == 1
    assert guard.accept_once(SESSION, "f" * 32) is False
    assert guard.accept_once(OTHER_SESSION, RID) is False


class FakeUnixPeer:
    family = socket.AF_UNIX
    def __init__(self, frame, *, uid=1001, timeout=0.1, family=None):
        self.data = bytearray(struct.pack("!I", len(frame)) + frame)
        self.uid = uid
        self.timeout = timeout
        if family is not None:
            self.family = family

    def getsockopt(self, level, optname, length):
        return struct.pack("3i", 333, self.uid, 100)

    def gettimeout(self):
        return self.timeout

    def recv(self, count):
        chunk = bytes(self.data[:count])
        del self.data[:count]
        return chunk


def test_connected_peer_accepts_strict_framed_bytes():
    peer = FakeUnixPeer(message())
    assert read_connected_frame(peer, expected_uid=1001) == message()


def test_unix_uid_and_timeout_and_family_required():
    for peer in (
        FakeUnixPeer(message(), uid=1002),
        FakeUnixPeer(message(), timeout=None),
        FakeUnixPeer(message(), timeout=15),
        FakeUnixPeer(message(), family=socket.AF_INET),
    ):
        with pytest.raises((PermissionError, ValueError)):
            read_connected_frame(peer, expected_uid=1001)


def test_truncated_and_oversized_frames_rejected():
    peer = FakeUnixPeer(b"x")
    peer.data = bytearray(struct.pack("!I", MAX_FRAME_BYTES+1))
    with pytest.raises(ValueError):
        read_connected_frame(peer, expected_uid=1001)
    peer = FakeUnixPeer(message())
    peer.data = peer.data[:-3]
    with pytest.raises(ValueError):
        read_connected_frame(peer, expected_uid=1001)


def bridge(core, *, enabled=True, peer=None, session=None, **flags):
    session = session or SESSION
    params = {
        "connection": peer or FakeUnixPeer(message()),
        "expected_uid": 1001,
        "secret": KEY,
        "active_session": session,
        "replay_guard": OneSessionReplayGuard(session_id=session),
        "handoff": AppLabFinalTextHandoff(core, enabled=True),
        "session_active": lambda: True,
        "asr_released": lambda: True,
        "stop_requested": lambda: False,
        "enabled": enabled,
        "clock": lambda: NOW,
    }
    params.update(flags)
    return run_authenticated_final_turn(**params)


def test_not_enabled_cannot_consume_frame():
    core = FakeCore()
    peer = FakeUnixPeer(message())
    assert bridge(core, peer=peer, enabled=False) == {"status": "disabled"}
    assert peer.data and core.calls == []


def test_authentic_frame_yields_private_answer_and_no_effectful_approval():
    core = FakeCore()
    result = bridge(core)
    assert result["status"] == "answer-ready"
    assert result["answer"] == "MyAI läste den svenska frågan."
    assert len(core.calls) == 1
    _, verifier = core.calls[0]
    assert verifier({"steps": [{"tool": "write_file"}]}, {}) is False


def test_wrong_uid_key_and_stale_frame_never_reach_core():
    for params in (
        {"peer": FakeUnixPeer(message(), uid=999)},
        {"secret": WRONG_KEY},
        {"peer": FakeUnixPeer(message(issued_at=NOW-31))},
    ):
        core = FakeCore()
        assert bridge(core, **params)["status"] == "authentication-or-frame-rejected"
        assert core.calls == []


@pytest.mark.parametrize("field", ["session_active", "asr_released", "stop_requested"])
def test_host_lifecycle_gate_fail_closed(field):
    core = FakeCore()
    peer = FakeUnixPeer(message())
    probe = (lambda: True) if field == "stop_requested" else (lambda: False)
    assert bridge(core, peer=peer, **{field: probe}) == {"status": "session-not-ready"}
    assert peer.data and core.calls == []


def test_one_handoff_and_replay_guard_rejects_duplicate_authenticated_message():
    core = FakeCore()
    replay = OneSessionReplayGuard(session_id=SESSION)
    handoff = AppLabFinalTextHandoff(core, enabled=True)
    args = {
        "replay_guard": replay, "handoff": handoff,
    }
    assert bridge(core, **args)["status"] == "answer-ready"
    assert bridge(core, **args)["status"] == "replay-or-capacity-rejected"
    assert len(core.calls) == 1


def test_stop_after_model_suppresses_private_answer():
    core = FakeCore()
    stop = [False]
    class StopCore:
        def respond_voice(self, text, *, plan_verifier):
            stop[0] = True
            return {"answer": "PRIVATE ANSWER"}
    assert bridge(StopCore(), stop_requested=lambda: stop[0]) == {
        "status": "cancelled"}


def test_no_socket_listening_audio_or_creds_in_source():
    import inspect
    import core.app_lab_unix_final_text as m
    src = inspect.getsource(m)
    for forbidden in (".bind(", ".listen(", "socket.socket(", "aplay",
                      "arecord", "Microphone(", "KokoroTTS(", "PiperVoice("):
        assert forbidden not in src
