"""Real Linux kernel socketpair tests; no server bind, model, microphone or TTS."""
import os
import socket
import struct
import threading
import time

import pytest

from core.app_lab_unix_final_text import (
    read_connected_frame, verify_signed_request,
)
from integrations.arduino_app_lab.alma_reference.private_reply import (
    OneSessionReplyGuard, frame_signed_reply, make_signed_reply,
)
from integrations.arduino_app_lab.alma_reference.private_socket_client import (
    exchange_final_over_connected_socket,
)

SID="a"*32
RID="b"*32
KEY=b"t"*32
NOW=1900000000
TEXT="Jag vill utveckla MyAI på svenska."


def _pair():
    if os.getuid() == 0:
        pytest.skip("Linux peer service UID must not be root")
    client, server = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    client.settimeout(0.5)
    server.settimeout(0.5)
    return client, server


def _invoke(client, *, guard=None, stopped=None, **kwargs):
    stopped = stopped or [False]
    args=dict(
        secret=KEY,session_id=SID,request_id=RID,issued_at=NOW,text=TEXT,
        expected_peer_uid=os.getuid(),
        reply_guard=guard or OneSessionReplyGuard(session_id=SID),
        session_active=lambda:True, asr_released=lambda:True,
        stop_requested=lambda:stopped[0],enabled=True,
        clock=lambda:NOW+1, max_wait_seconds=2.5,
    )
    args.update(kwargs)
    return exchange_final_over_connected_socket(client, **args)


def _serve(server, *, answer=None, request_mutator=None, raw_reply=None):
    try:
        data=read_connected_frame(server,expected_uid=os.getuid())
        message=verify_signed_request(data,secret=KEY,active_session=SID,now=NOW)
        if request_mutator:
            request_mutator(message)
        if raw_reply is None:
            reply=make_signed_reply(
                result=answer or {
                    "status":"answer-ready","answer":"Hej från MyAI.",
                    "tool_execution_status":"not_applicable",
                    "manual_reconciliation_required":False,
                    "tool_dispatch_blocked":False,
                },
                secret=KEY,session_id=SID,request_id=message["request_id"],
                issued_at=NOW+1,
            )
            raw_reply=frame_signed_reply(reply)
        server.sendall(raw_reply)
    except (BrokenPipeError, OSError):
        pass
    finally:
        server.close()


def _roundtrip(*, answer=None, guard=None, raw_reply=None, **kwargs):
    client, server=_pair()
    worker=threading.Thread(target=_serve,
          kwargs={"server":server,"answer":answer,"raw_reply":raw_reply})
    worker.start()
    try:
        return _invoke(client,guard=guard,**kwargs)
    finally:
        client.close()
        worker.join(timeout=3)
        assert not worker.is_alive()


def test_real_connected_unix_roundtrip():
    assert _roundtrip()=={"status":"ready","answer":"Hej från MyAI."}


def test_partial_or_blocked_backend_never_speaks():
    result={
       "status":"review-required","answer":"SECRET NOT FOR TTS",
       "tool_execution_status":"unknown",
       "manual_reconciliation_required":True,
    }
    assert _roundtrip(answer=result)=={"status":"withheld"}


def test_wrong_kernel_peer_uid_refused_before_send():
    client,server=_pair()
    try:
        out=_invoke(client,expected_peer_uid=os.getuid()+1)
        assert out=={"status":"private-exchange-rejected"}
        server.settimeout(.05)
        with pytest.raises(socket.timeout):
            server.recv(1)
    finally:
        client.close()
        server.close()


def test_disabled_mode_never_transmits():
    client,server=_pair()
    try:
        assert _invoke(client,enabled=False)=={"status":"disabled"}
        with pytest.raises(socket.timeout):
            server.settimeout(.05)
            server.recv(1)
    finally:
        client.close()
        server.close()


def test_asr_not_released_never_transmits():
    client,server=_pair()
    try:
        assert _invoke(client,asr_released=lambda:False)=={"status":"session-not-ready"}
        with pytest.raises(socket.timeout):
            server.settimeout(.05)
            server.recv(1)
    finally:
        client.close()
        server.close()


def test_stop_before_send_never_transmits():
    client,server=_pair()
    try:
        assert _invoke(client,stopped=[True])=={"status":"session-not-ready"}
        with pytest.raises(socket.timeout):
            server.settimeout(.05)
            server.recv(1)
    finally:
        client.close()
        server.close()


def test_wrong_request_identity_rejected():
    reply=make_signed_reply(
        result={"status":"answer-ready","answer":"Mismatch",
                "tool_execution_status":"not_applicable",
                "manual_reconciliation_required":False,
                "tool_dispatch_blocked":False},
        secret=KEY,session_id=SID,request_id="f"*32,issued_at=NOW+1,
    )
    assert _roundtrip(raw_reply=frame_signed_reply(reply))=={
        "status":"private-exchange-rejected"
    }


def test_replay_reply_id_accepted_once():
    guard=OneSessionReplyGuard(session_id=SID)
    assert _roundtrip(guard=guard)=={"status":"ready","answer":"Hej från MyAI."}
    assert _roundtrip(guard=guard)=={"status":"private-exchange-rejected"}


@pytest.mark.parametrize("bad", [
    b"",
    struct.pack("!I",0),
    struct.pack("!I",5000),
    struct.pack("!I",10)+b"hi",
])
def test_bad_or_truncated_reply_is_rejected(bad):
    # A bare empty reply closes the connection: no indefinite read.
    assert _roundtrip(raw_reply=bad)=={"status":"private-exchange-rejected"}


def test_stop_during_reply_wait():
    client,server=_pair()
    stopped=[False]
    ready=threading.Event()
    def no_answer():
        try:
            message=read_connected_frame(server,expected_uid=os.getuid())
            assert message
            ready.set()
            # Wait for the caller to withdraw consent, without speaking.
            while not stopped[0]:
                time.sleep(.01)
        finally:
            server.close()
    worker=threading.Thread(target=no_answer)
    worker.start()
    def cancel():
        assert ready.wait(2)
        stopped[0]=True
    stop_worker=threading.Thread(target=cancel)
    stop_worker.start()
    try:
        assert _invoke(client,stopped=stopped)=={"status":"private-exchange-rejected"}
    finally:
        stopped[0]=True
        client.close()
        worker.join(3)
        stop_worker.join(3)


def test_timeout_without_reply_is_bounded():
    client,server=_pair()
    try:
        start=time.monotonic()
        out=_invoke(client,max_wait_seconds=.15)
        assert out=={"status":"private-exchange-rejected"}
        assert time.monotonic()-start<1.5
    finally:
        client.close()
        server.close()


@pytest.mark.parametrize("timeout", [0,None,4,True])
def test_invalid_socket_timeout_refused(timeout):
    client,server=_pair()
    try:
        client.settimeout(timeout)
        assert _invoke(client)=={"status":"private-exchange-rejected"}
    finally:
        client.close()
        server.close()
