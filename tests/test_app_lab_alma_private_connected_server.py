"""Real Linux Unix socketpair integration of MyAI handoff and private reply.

No socket bind/listen, audio capture/playback, model, filesystem or network.
"""
import os
import socket
import struct
import threading
import time

import pytest

from core.app_lab_unix_final_text import (
    OneSessionReplayGuard, make_signed_request,
)
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from core.app_lab_private_reply_server import serve_one_authenticated_connected_turn
from integrations.arduino_app_lab.alma_reference.private_reply import OneSessionReplyGuard
from integrations.arduino_app_lab.alma_reference.private_socket_client import (
    exchange_final_over_connected_socket,
)

SESSION = "c" * 32
REQUEST = "d" * 32
SECRET = b"q" * 32
NOW = 1_900_000_000
TEXT = "Jag vill utveckla min svenska assistent."


class FakeCore:
    def __init__(self, response=None, *, memory=None, on_respond=None):
        self.settings = {"memory": memory if memory is not None else {
            "auto_assess_enabled": False, "auto_save_enabled": False,
            "review_queue_enabled": False, "lifecycle_enabled": False,
        }}
        self.calls = []
        self.response = response or {
            "answer": "Jag hjälper dig att utveckla MyAI.",
            "tool_execution_status": "not_applicable",
            "manual_reconciliation_required": False,
            "tool_dispatch_blocked": False,
        }
        self.on_respond = on_respond

    def respond_voice(self, text, *, plan_verifier):
        self.calls.append(text)
        assert plan_verifier({"steps": [{"tool": "write_file"}]}, {}) is False
        if self.on_respond:
            self.on_respond()
        return self.response


def _pair():
    if os.getuid() == 0:
        pytest.skip("SO_PEERCRED fixture requires a non-root Linux runner")
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    a.settimeout(0.5)
    b.settimeout(0.5)
    return a, b


def _run(client, server, *, core=None, request_guard=None,
         reply_guard=None, stopped=None, server_overrides=None,
         client_overrides=None):
    stopped = stopped if stopped is not None else [False]
    core = core or FakeCore()
    results = []
    common = dict(
        secret=SECRET,
        session_active=lambda: True,
        asr_released=lambda: True,
        stop_requested=lambda: stopped[0],
        enabled=True,
        clock=lambda: NOW + 1,
    )
    serv_opts = dict(
        expected_peer_uid=os.getuid(),
        active_session=SESSION,
        request_guard=request_guard or OneSessionReplayGuard(session_id=SESSION),
        handoff=AppLabFinalTextHandoff(core, enabled=True),
        **common,
    )
    serv_opts.update(server_overrides or {})
    def server_thread():
        try:
            results.append(serve_one_authenticated_connected_turn(server, **serv_opts))
        finally:
            server.close()
    t = threading.Thread(target=server_thread)
    t.start()
    client_opts = dict(
        expected_peer_uid=os.getuid(),
        session_id=SESSION, request_id=REQUEST, issued_at=NOW, text=TEXT,
        reply_guard=reply_guard or OneSessionReplyGuard(session_id=SESSION),
        max_wait_seconds=2.0,
        **common,
    )
    client_opts.update(client_overrides or {})
    try:
        answer = exchange_final_over_connected_socket(client, **client_opts)
    finally:
        client.close()
        t.join(timeout=3)
        assert not t.is_alive()
    return answer, results[0], core


def test_full_connected_myai_to_alma_turn():
    client, server = _pair()
    answer, result, core = _run(client, server)
    assert answer == {"status": "ready", "answer": "Jag hjälper dig att utveckla MyAI."}
    assert result == {"status": "sent", "reply_status": "ready"}
    assert core.calls == [TEXT]


def test_blocked_write_action_never_reaches_alma_answer():
    core = FakeCore(response={
        "answer": "I secretly wrote a file", "tool_execution_status": "blocked",
        "manual_reconciliation_required": False, "tool_dispatch_blocked": True,
    })
    c, s = _pair()
    answer, result, _ = _run(c, s, core=core)
    assert answer == {"status": "withheld"}
    assert result == {"status": "sent", "reply_status": "withheld"}


@pytest.mark.parametrize("state", ["unknown", "partially_completed", "failed", "not_run"])
def test_uncertain_or_failed_tools_withhold_voice(state):
    core = FakeCore(response={
        "answer": "Unsafe backend output", "tool_execution_status": state,
        "manual_reconciliation_required": False,
    })
    c, s = _pair()
    answer, result, _ = _run(c, s, core=core)
    assert answer == {"status": "withheld"}
    assert result["reply_status"] == "withheld"


def test_unsafe_memory_policy_refuses_dispatch():
    core = FakeCore(memory={"auto_save_enabled": True})
    c, s = _pair()
    answer, server_status, _ = _run(c, s, core=core)
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "memory-policy-unsafe"}
    assert core.calls == []


def test_wrong_kernel_peer_identity_never_dispatches():
    c, s = _pair()
    answer, server_status, core = _run(
        c, s, server_overrides={"expected_peer_uid": os.getuid() + 1},
    )
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "authentication-or-frame-rejected"}
    assert core.calls == []


def test_wrong_mac_refuses_before_dispatch():
    c, s = _pair()
    answer, server_status, core = _run(
        c, s, client_overrides={"secret": b"z" * 32},
    )
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "authentication-or-frame-rejected"}
    assert core.calls == []


def test_stopped_before_send_cannot_dispatch():
    c, s = _pair()
    answer, server_status, core = _run(c, s, stopped=[True])
    assert answer == {"status": "session-not-ready"}
    assert server_status == {"status": "session-not-ready"}
    assert core.calls == []


def test_audio_not_released_never_dispatches():
    c, s = _pair()
    answer, server_status, core = _run(
        c, s, server_overrides={"asr_released": lambda: False},
    )
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "session-not-ready"}
    assert core.calls == []


def test_cancelled_while_myai_answers_sends_no_reply():
    stopped = [False]
    core = FakeCore(on_respond=lambda: stopped.__setitem__(0, True))
    c, s = _pair()
    answer, server_status, _ = _run(c, s, stopped=stopped, core=core)
    assert answer["status"] != "ready"
    assert server_status == {"status": "session-not-ready"}
    assert core.calls == [TEXT]


def test_invalid_response_type_withheld_without_original_details():
    core = FakeCore(response={
        "answer": "PRIVATE CONTENT", "tool_execution_status": [],
        "manual_reconciliation_required": True,
    })
    c, s = _pair()
    answer, server_status, _ = _run(c, s, core=core)
    assert answer == {"status": "withheld"}
    assert server_status == {"status": "sent", "reply_status": "withheld"}


def test_replay_of_same_signed_request_dispatches_only_once():
    guard = OneSessionReplayGuard(session_id=SESSION)
    core = FakeCore()
    c1, s1 = _pair()
    answer1, stat1, _ = _run(c1, s1, core=core, request_guard=guard)
    c2, s2 = _pair()
    answer2, stat2, _ = _run(c2, s2, core=core, request_guard=guard)
    assert answer1["status"] == "ready"
    assert answer2 == {"status": "private-exchange-rejected"}
    assert stat2 == {"status": "replay-or-capacity-rejected"}
    assert core.calls == [TEXT]


def test_not_enabled_never_reads_or_dispatches():
    core = FakeCore()
    c, s = _pair()
    answer, server_status, _ = _run(
        c, s, core=core, server_overrides={"enabled": False},
    )
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "disabled"}
    assert core.calls == []


def test_server_rejects_invalid_secret_without_reading():
    core = FakeCore()
    c, s = _pair()
    answer, server_status, _ = _run(
        c, s, core=core, server_overrides={"secret": b"x"},
    )
    assert answer == {"status": "private-exchange-rejected"}
    assert server_status == {"status": "server-not-configured"}
    assert core.calls == []


def test_server_reply_binds_exact_request_id():
    c, s = _pair()
    answer, status, core = _run(
        c, s, client_overrides={"request_id": "e" * 32},
    )
    assert answer["status"] == "ready"
    assert status["reply_status"] == "ready"
    assert core.calls == [TEXT]


def test_empty_llm_answer_is_withheld():
    core = FakeCore(response={
        "answer": "", "tool_execution_status": "not_applicable",
        "manual_reconciliation_required": False,
    })
    c, s = _pair()
    answer, status, _ = _run(c, s, core=core)
    assert answer == {"status": "withheld"}
    assert status["reply_status"] == "withheld"
