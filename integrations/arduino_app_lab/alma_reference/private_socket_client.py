"""Opt-in private App Lab FINAL TEXT request/reply over an existing AF_UNIX socket.

Pure source-stage client. Never opens/binds/listens for a socket, provisions a
key, records audio, performs playback, writes transcript files or logs text.
The caller owns a verified final ASR event, session identities, a connected
private socket, a fresh session key, physical ASR release and a Stop signal.
The server is not implemented here and must separately authorize everything.
"""
from __future__ import annotations

import math
import select
import socket
import struct
import time

from integrations.arduino_app_lab.alma_reference.source_contract import sign_final_for_myai
from integrations.arduino_app_lab.alma_reference.private_reply import (
    MAX_REPLY_BYTES,
    OneSessionReplyGuard,
    verify_signed_reply,
)

MAX_SEND_TIMEOUT_SECONDS = 3.0
MAX_WAIT_SECONDS = 90.0
_MAX_REQUEST_BYTES = 2048
_PEERCRED = struct.Struct("3i")
_LENGTH = struct.Struct("!I")


def _ready(session_active, asr_released, stop_requested):
    try:
        return (
            session_active() is True
            and asr_released() is True
            and stop_requested() is False
        )
    except BaseException:
        return False


def _socket_preflight(connection, expected_uid):
    if getattr(connection, "family", None) != socket.AF_UNIX or not hasattr(socket, "SO_PEERCRED"):
        raise PermissionError("Linux AF_UNIX is required")
    if type(expected_uid) is not int or expected_uid <= 0:
        raise ValueError("Explicit positive peer UID required")
    try:
        raw = connection.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, _PEERCRED.size
        )
        timeout = connection.gettimeout()
        pid, uid, gid = _PEERCRED.unpack(raw)
    except (AttributeError, OSError, TypeError, ValueError, struct.error) as exc:
        raise PermissionError("Peer verification unavailable") from exc
    if (type(raw) is not bytes or len(raw) != _PEERCRED.size
            or pid <= 0 or uid != expected_uid or gid < 0):
        raise PermissionError("Untrusted local peer")
    if (type(timeout) not in (int, float)
            or not math.isfinite(timeout)
            or not 0 < timeout <= MAX_SEND_TIMEOUT_SECONDS):
        raise ValueError("Finite bounded socket send timeout required")


def _recv_exact(connection, size, *, deadline, stop_requested):
    chunks = bytearray()
    while len(chunks) < size:
        if stop_requested() is not False:
            raise ValueError("Turn cancelled")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Private reply timed out")
        readable, _, _ = select.select([connection], [], [], min(0.20, remaining))
        if not readable:
            continue
        data = connection.recv(size - len(chunks))
        if not data:
            raise ValueError("Truncated private reply")
        chunks.extend(data)
    return bytes(chunks)


def _read_reply(connection, *, stop_requested, max_wait_seconds):
    deadline = time.monotonic() + max_wait_seconds
    length = _LENGTH.unpack(_recv_exact(
        connection, _LENGTH.size,
        deadline=deadline, stop_requested=stop_requested,
    ))[0]
    if not 0 < length <= MAX_REPLY_BYTES:
        raise ValueError("Unbounded private reply")
    return _recv_exact(
        connection, length, deadline=deadline, stop_requested=stop_requested,
    )


def exchange_final_over_connected_socket(
    connection, *, secret, session_id, request_id, issued_at, text,
    expected_peer_uid, reply_guard, session_active, asr_released,
    stop_requested, enabled=False, clock=None, max_wait_seconds=45.0,
):
    """Send a signed final-text request, accept its exact signed reply once.

    The only 'ready' result holds authenticated answer text. No actual
    synthesis or playback happens here. A separate, immediately-before-TTS
    Stop/session check is mandatory for any future real App Lab integration.
    """
    if enabled is not True:
        return {"status": "disabled"}
    if (not isinstance(reply_guard, OneSessionReplyGuard)
            or reply_guard.session_id != session_id
            or not all(callable(x) for x in
                       (session_active, asr_released, stop_requested))):
        return {"status": "client-not-configured"}
    if (type(max_wait_seconds) not in (int, float)
            or not math.isfinite(max_wait_seconds)
            or not 0 < max_wait_seconds <= MAX_WAIT_SECONDS):
        return {"status": "client-not-configured"}
    if not _ready(session_active, asr_released, stop_requested):
        return {"status": "session-not-ready"}
    try:
        _socket_preflight(connection, expected_peer_uid)
        request = sign_final_for_myai(
            text, secret=secret, session_id=session_id,
            request_id=request_id, issued_at=issued_at,
        )
        if not 0 < len(request) <= _MAX_REQUEST_BYTES:
            raise ValueError("Oversized request")
        if not _ready(session_active, asr_released, stop_requested):
            return {"status": "session-not-ready"}
        connection.sendall(_LENGTH.pack(len(request)) + request)
        reply = _read_reply(
            connection, stop_requested=stop_requested,
            max_wait_seconds=float(max_wait_seconds),
        )
        if not _ready(session_active, asr_released, stop_requested):
            return {"status": "session-not-ready"}
        current = (clock or time.time)()
        result = verify_signed_reply(
            reply, secret=secret, active_session=session_id,
            expected_request=request_id, now=current,
            replay_guard=reply_guard, stop_requested=stop_requested,
        )
        if not _ready(session_active, asr_released, stop_requested):
            return {"status": "session-not-ready"}
        return result
    except (ValueError, PermissionError, OSError, TimeoutError,
            TypeError, OverflowError, struct.error):
        # No raw user speech, credentials, peer identifiers or socket paths.
        return {"status": "private-exchange-rejected"}
