"""Disabled-by-default, single-turn authenticated AF_UNIX MyAI reply handler.

Accepts an ALREADY CONNECTED socket and an ALREADY CONSTRUCTED MyAI handoff.
No bind/listen/connect, key creation, service startup, audio access, model
loading, filesystem writes or untrusted tool approval occur in this module.
Physical mic release and Stop callbacks must be supplied by the trusted host;
the callbacks are NOT proof of actual hardware lifecycle.
"""
from __future__ import annotations

import json
import math
import time

from core.app_lab_unix_final_text import (
    OneSessionReplayGuard,
    _automatic_memory_writes_disabled,
    read_connected_frame,
    verify_signed_request,
)
from core.app_lab_voice_handoff import AppLabFinalTextHandoff
from integrations.arduino_app_lab.alma_reference.private_reply import (
    frame_signed_reply,
    make_signed_reply,
)


def _ready(session_active, asr_released, stop_requested):
    try:
        return (
            session_active() is True
            and asr_released() is True
            and stop_requested() is False
        )
    except BaseException:
        return False


def _timestamp(clock):
    value = (clock or time.time)()
    if (type(value) not in (int, float)
            or not math.isfinite(value) or value < 0):
        raise ValueError("Invalid host clock")
    return int(value)


def serve_one_authenticated_connected_turn(
    connection, *, expected_peer_uid, secret, active_session,
    request_guard, handoff, session_active, asr_released, stop_requested,
    enabled=False, clock=None,
):
    """Verify one request, dispatch to MyAI, send a correlated signed reply.

    Returns status metadata ONLY; never returns a raw answer or transcript.
    Rejects unknown peers, stale requests, replay, unsafe memory settings,
    stopped sessions and unauthenticated frames without dispatching a tool.
    """
    if enabled is not True:
        return {"status": "disabled"}
    if (type(secret) is not bytes or len(secret) != 32
            or not isinstance(request_guard, OneSessionReplayGuard)
            or request_guard.session_id != active_session
            or not isinstance(handoff, AppLabFinalTextHandoff)
            or getattr(handoff, "_enabled", False) is not True
            or not all(callable(x) for x in
                       (session_active, asr_released, stop_requested))):
        return {"status": "server-not-configured"}

    # An authenticated exchange alone does NOT grant persistent memory writes
    # or effectful tools. Do not start a request with unsafe memory policy.
    if not _automatic_memory_writes_disabled(handoff):
        return {"status": "memory-policy-unsafe"}
    if not _ready(session_active, asr_released, stop_requested):
        return {"status": "session-not-ready"}

    try:
        frame = read_connected_frame(connection, expected_uid=expected_peer_uid)
        message = verify_signed_request(
            frame, secret=secret, active_session=active_session,
            now=_timestamp(clock),
        )
    except (ValueError, PermissionError, OSError, TimeoutError,
            TypeError, OverflowError):
        return {"status": "authentication-or-frame-rejected"}

    # Burn this request identity atomically BEFORE calling the potentially
    # effectful MyAI core, including for requests later cancelled.
    if not request_guard.accept_once(active_session, message["request_id"]):
        return {"status": "replay-or-capacity-rejected"}
    if not _ready(session_active, asr_released, stop_requested):
        return {"status": "session-not-ready"}
    if not _automatic_memory_writes_disabled(handoff):
        return {"status": "memory-policy-unsafe"}

    try:
        outcome = handoff.dispatch(
            message["text"], session_active=True, asr_released=True,
            stop_requested=stop_requested,
        )
    except Exception:
        # Do not risk sending a backend exception or private speech text.
        return {"status": "dispatch-rejected"}

    if not _ready(session_active, asr_released, stop_requested):
        return {"status": "session-not-ready"}
    if not _automatic_memory_writes_disabled(handoff):
        return {"status": "memory-policy-unsafe"}

    try:
        reply = make_signed_reply(
            result=outcome, secret=secret,
            session_id=message["session_id"],
            request_id=message["request_id"],
            issued_at=_timestamp(clock),
        )
        reply_status = json.loads(reply.decode("utf-8", "strict"))["status"]
        # Last cooperative Stop/session check immediately before socket send.
        if not _ready(session_active, asr_released, stop_requested):
            return {"status": "session-not-ready"}
        connection.sendall(frame_signed_reply(reply))
    except (ValueError, TypeError, UnicodeError, OSError,
            TimeoutError, OverflowError):
        return {"status": "response-not-sent"}

    # Status-only observability: never put speech or backend text in result.
    return {"status": "sent", "reply_status": reply_status}
