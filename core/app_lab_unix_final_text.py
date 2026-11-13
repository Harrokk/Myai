"""Opt-in Unix-socket final-text authentication, with no socket listener.

This is a source-only protocol boundary for a *future* operator-owned App Lab
bridge. It never binds/listens/connects, records audio, logs text, creates
credentials, starts services, or loads AI models.

The host must provision a fresh secret through a private trusted channel,
create an AF_UNIX socket with correct ACL/mount namespace, and independently
establish physical session consent, microphone release, and Stop state.
None of those capabilities are supplied by this module.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import socket
import struct
import threading
import time
import unicodedata

from core.selfdev_unix_peercred import require_peer_uid

PROTOCOL_VERSION = 1
MAX_FRAME_BYTES = 2048
MAX_TEXT_CHARS = 500
MAX_WALL_AGE_SECONDS = 30
MAX_FUTURE_SKEW_SECONDS = 2
MAX_TIMEOUT_SECONDS = 3.0
_DOMAIN = b"MyAI-AppLab-FinalText-2026-11-13\x00"
_HEX_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAC_HEX = re.compile(r"[0-9a-f]{64}\Z")
_LENGTH = struct.Struct("!I")
_KEYS = frozenset({
    "version", "action", "session_id", "request_id",
    "issued_at", "text", "mac",
})
_BODY_KEYS = _KEYS - {"mac"}


def _valid_text(text):
    return (
        type(text) is str
        and 0 < len(text.strip()) <= MAX_TEXT_CHARS
        and len(text) <= MAX_TEXT_CHARS
        and all(unicodedata.category(c) not in {"Cc", "Cf", "Cs"}
                for c in text)
    )


def _json_bytes(payload):
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False,
    ).encode("utf-8", "strict")


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate message field")
        result[key] = value
    return result


def _bad_constant(_value):
    raise ValueError("Invalid non-finite number")


def _valid_key(secret):
    return type(secret) is bytes and len(secret) == 32


def _body(session_id, request_id, issued_at, text):
    if (type(session_id) is not str or not _HEX_ID.fullmatch(session_id)
            or type(request_id) is not str or not _HEX_ID.fullmatch(request_id)
            or type(issued_at) is not int or issued_at < 0
            or not _valid_text(text)):
        raise ValueError("Invalid final-text request")
    return {
        "version": PROTOCOL_VERSION,
        "action": "submit_final",
        "session_id": session_id,
        "request_id": request_id,
        "issued_at": issued_at,
        "text": text,
    }


def make_signed_request(*, secret, session_id, request_id, issued_at, text):
    """Pure client-side encoder. This does not transmit or collect audio."""
    if not _valid_key(secret):
        raise ValueError("A private 32-byte session key is required")
    payload = _body(session_id, request_id, issued_at, text)
    digest = hmac.new(secret, _DOMAIN + _json_bytes(payload),
                      hashlib.sha256).hexdigest()
    payload["mac"] = digest
    data = _json_bytes(payload)
    if not 0 < len(data) <= MAX_FRAME_BYTES:
        raise ValueError("Final-text request exceeds frame budget")
    return data


def verify_signed_request(data, *, secret, active_session, now):
    """Check strict schema, HMAC, active session and expiration; no replay IO."""
    if not _valid_key(secret):
        raise ValueError("A private 32-byte session key is required")
    if (type(data) is not bytes or not 0 < len(data) <= MAX_FRAME_BYTES
            or type(active_session) is not str
            or not _HEX_ID.fullmatch(active_session)
            or type(now) not in (int, float)
            or not 0 <= now < float("inf")):
        raise ValueError("Unusable authenticated request boundary")
    try:
        message = json.loads(
            data.decode("utf-8", "strict"),
            object_pairs_hook=_unique_keys, parse_constant=_bad_constant,
        )
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise ValueError("Invalid authenticated message") from exc
    if type(message) is not dict or set(message) != _KEYS:
        raise ValueError("Unexpected authenticated message fields")
    mac = message.pop("mac")
    if type(mac) is not str or _MAC_HEX.fullmatch(mac) is None:
        raise ValueError("Invalid request authenticator")
    try:
        rebuilt = _body(
            message["session_id"], message["request_id"],
            message["issued_at"], message["text"],
        )
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Invalid authenticated request") from exc
    if message != rebuilt or message["session_id"] != active_session:
        raise ValueError("Incorrect active session")
    expected = hmac.new(secret, _DOMAIN + _json_bytes(rebuilt),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(mac, expected):
        raise ValueError("Bad authenticated message")
    age = now - message["issued_at"]
    if age > MAX_WALL_AGE_SECONDS or age < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("Expired or future-dated message")
    return message


class OneSessionReplayGuard:
    """Fail-closed in-memory request-ID set; caller owns lifetime and sessions."""

    def __init__(self, *, session_id, max_requests=128):
        if type(session_id) is not str or not _HEX_ID.fullmatch(session_id):
            raise ValueError("Invalid session identity")
        if type(max_requests) is not int or not 1 <= max_requests <= 1024:
            raise ValueError("Invalid replay capacity")
        self.session_id = session_id
        self.max_requests = max_requests
        self._ids = set()
        self._lock = threading.Lock()

    def accept_once(self, session_id, request_id):
        if session_id != self.session_id:
            return False
        if type(request_id) is not str or not _HEX_ID.fullmatch(request_id):
            return False
        with self._lock:
            if request_id in self._ids or len(self._ids) >= self.max_requests:
                return False
            self._ids.add(request_id)
            return True



def _automatic_memory_writes_disabled(handoff):
    """Reject mutable memory policies until a separate consented write design."""
    assistant = getattr(handoff, "_assistant", None)
    settings = getattr(assistant, "settings", None)
    if type(settings) is not dict:
        return False
    memory = settings.get("memory")
    if type(memory) is not dict:
        return False
    return all(memory.get(key) is False for key in (
        "auto_assess_enabled", "auto_save_enabled",
        "review_queue_enabled", "lifecycle_enabled",
    ))

def read_connected_frame(connection, *, expected_uid):
    """Read from an already connected, kernel-authenticated AF_UNIX peer.

    This module never creates or binds a Unix socket. The creator must
    configure an isolated filesystem socket path and service identity.
    """
    if getattr(connection, "family", None) != socket.AF_UNIX:
        raise PermissionError("Only a private Unix-socket peer is accepted")
    require_peer_uid(connection, expected_uid=expected_uid)
    try:
        timeout = connection.gettimeout()
    except (OSError, AttributeError) as exc:
        raise ValueError("Bounded socket timeout required") from exc
    if (type(timeout) not in (int, float)
            or not 0 < timeout <= MAX_TIMEOUT_SECONDS):
        raise ValueError("Socket must have a bounded receive timeout")

    deadline = time.monotonic() + MAX_TIMEOUT_SECONDS
    def exact(count):
        chunks = bytearray()
        while len(chunks) < count:
            if time.monotonic() >= deadline:
                raise ValueError("IPC frame timed out")
            part = connection.recv(count - len(chunks))
            if not part:
                raise ValueError("Truncated IPC frame")
            chunks.extend(part)
        return bytes(chunks)

    size = _LENGTH.unpack(exact(_LENGTH.size))[0]
    if not 0 < size <= MAX_FRAME_BYTES:
        raise ValueError("Oversized IPC frame")
    return exact(size)


def run_authenticated_final_turn(
    connection, *, expected_uid, secret, active_session, replay_guard,
    handoff, session_active, asr_released, stop_requested, enabled=False,
    clock=None,
):
    """Authenticate one input frame and forward it to disabled-by-default glue.

    No response is written to the socket; the returned object stays private
    in the caller process. session_active/asr_released/stop_requested are
    trusted HOST callbacks, never claims accepted from message JSON.
    """
    if enabled is not True:
        return {"status": "disabled"}
    if (not isinstance(replay_guard, OneSessionReplayGuard)
            or replay_guard.session_id != active_session
            or handoff is None
            or not callable(getattr(handoff, "dispatch", None))
            or not all(callable(x) for x in
                       (session_active, asr_released, stop_requested))):
        return {"status": "bridge-not-configured"}

    # Even non-effectful voice tool plans may trigger MyAICore memory writes.
    # Do not enable this initial transport with automatic persistence active.
    if not _automatic_memory_writes_disabled(handoff):
        return {"status": "memory-policy-unsafe"}

    try:
        if (session_active() is not True
                or asr_released() is not True
                or stop_requested() is not False):
            return {"status": "session-not-ready"}
    except BaseException:
        return {"status": "session-not-ready"}

    try:
        frame = read_connected_frame(connection, expected_uid=expected_uid)
        current = (clock or time.time)()
        message = verify_signed_request(
            frame, secret=secret, active_session=active_session, now=current,
        )
    except (ValueError, PermissionError, OSError, TimeoutError,
            TypeError, OverflowError):
        return {"status": "authentication-or-frame-rejected"}

    if not replay_guard.accept_once(active_session, message["request_id"]):
        return {"status": "replay-or-capacity-rejected"}
    try:
        if (session_active() is not True
                or asr_released() is not True
                or stop_requested() is not False):
            return {"status": "session-not-ready"}
    except BaseException:
        return {"status": "session-not-ready"}

    # Refuse settings changed by another component during authentication.
    if not _automatic_memory_writes_disabled(handoff):
        return {"status": "memory-policy-unsafe"}

    return handoff.dispatch(
        message["text"], session_active=True, asr_released=True,
        stop_requested=stop_requested,
    )
