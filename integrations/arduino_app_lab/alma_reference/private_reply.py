"""Portable, source-only signed response format for a future private App Lab bridge.

No socket calls, recording, playback, model or key management. Client must own
an authenticated channel, one fresh session secret, the outstanding request ID
and a live Stop signal before any future TTS playback.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import math
import re
import struct
import threading
import unicodedata

VERSION = 1
MAX_REPLY_BYTES = 4096
MAX_ANSWER_CHARS = 1200
MAX_AGE_SECONDS = 60
MAX_FUTURE_SKEW_SECONDS = 2
_DOMAIN = b"MyAI-AppLab-PrivateReply-v1\x00"  # distinct from request MAC domain
_ID = re.compile(r"[0-9a-f]{32}\Z")
_MAC = re.compile(r"[0-9a-f]{64}\Z")
_LENGTH = struct.Struct("!I")
_REQUIRED = frozenset({
    "version", "action", "session_id", "request_id", "issued_at",
    "status", "answer", "mac",
})


def _canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


def _unique(pairs):
    value = {}
    for key, data in pairs:
        if key in value:
            raise ValueError("Duplicate reply field")
        value[key] = data
    return value


def _no_constant(_value):
    raise ValueError("Invalid reply number")


def _valid_text(value):
    return (type(value) is str and 0 < len(value.strip()) <= MAX_ANSWER_CHARS
            and len(value) <= MAX_ANSWER_CHARS
            and all(unicodedata.category(ch) not in {"Cc", "Cf", "Cs"}
                    for ch in value))


def _ids(session_id, request_id, issued_at):
    return (type(session_id) is str and _ID.fullmatch(session_id) is not None
            and type(request_id) is str and _ID.fullmatch(request_id) is not None
            and type(issued_at) is int and issued_at >= 0)


def _body(session_id, request_id, issued_at, status, answer):
    if not _ids(session_id, request_id, issued_at):
        raise ValueError("Bad reply identity")
    if status not in ("ready", "withheld") or type(status) is not str:
        raise ValueError("Bad reply state")
    if status == "ready" and not _valid_text(answer):
        raise ValueError("Invalid final answer")
    if status == "withheld" and answer != "":
        raise ValueError("Withheld reply must not include answer")
    return {"version": VERSION, "action": "final_answer",
            "session_id": session_id, "request_id": request_id,
            "issued_at": issued_at, "status": status, "answer": answer}


def make_signed_reply(*, result, secret, session_id, request_id, issued_at):
    """Create a signed private reply; unsafe or uncertain results are withheld.

    Only a trusted result from an already completed and verified MyAI handoff
    belongs here. Never call this with arbitrary App Lab/user-supplied data.
    """
    if type(secret) is not bytes or len(secret) != 32:
        raise ValueError("A private 32-byte session key is required")
    if not _ids(session_id, request_id, issued_at):
        raise ValueError("Bad reply identity")
    safe = (type(result) is dict
            and result.get("status") == "answer-ready"
            and result.get("manual_reconciliation_required") is False
            and result.get("tool_execution_status") in ("not_applicable", "completed")
            and result.get("tool_dispatch_blocked") is not True
            and _valid_text(result.get("answer")))
    status = "ready" if safe else "withheld"
    answer = result["answer"].strip() if safe else ""
    body = _body(session_id, request_id, issued_at, status, answer)
    body["mac"] = hmac.new(secret, _DOMAIN + _canonical(body),
                           hashlib.sha256).hexdigest()
    encoded = _canonical(body)
    # Multi-byte UTF-8 can exceed this byte budget even within char limit.
    if len(encoded) > MAX_REPLY_BYTES:
        # Do not truncate answer into an unintended meaning. Fail closed.
        if status == "ready":
            return make_signed_reply(result=None, secret=secret,
                                     session_id=session_id, request_id=request_id,
                                     issued_at=issued_at)
        raise ValueError("Reply frame too large")
    return encoded


class OneSessionReplyGuard:
    """In-memory one-use response IDs; caller must rotate session and key."""

    def __init__(self, *, session_id, max_replies=128):
        if type(session_id) is not str or _ID.fullmatch(session_id) is None:
            raise ValueError("Invalid session")
        if type(max_replies) is not int or not 1 <= max_replies <= 1024:
            raise ValueError("Invalid capacity")
        self.session_id = session_id
        self.max_replies = max_replies
        self._seen = set()
        self._lock = threading.Lock()

    def accept_once(self, request_id):
        if type(request_id) is not str or _ID.fullmatch(request_id) is None:
            return False
        with self._lock:
            if request_id in self._seen or len(self._seen) >= self.max_replies:
                return False
            self._seen.add(request_id)
            return True


def verify_signed_reply(data, *, secret, active_session, expected_request,
                        now, replay_guard, stop_requested):
    """Authenticate a response and return a TTS-eligible answer at most once.

    Return {'status':'ready','answer':...} or {'status':'withheld'}.
    Fail closed for invalid signatures, sessions, stale replies, Stop and replay.
    """
    if type(secret) is not bytes or len(secret) != 32:
        raise ValueError("Missing private reply key")
    if (type(data) is not bytes or not 0 < len(data) <= MAX_REPLY_BYTES
            or type(active_session) is not str or _ID.fullmatch(active_session) is None
            or type(expected_request) is not str or _ID.fullmatch(expected_request) is None
            or not isinstance(replay_guard, OneSessionReplyGuard)
            or replay_guard.session_id != active_session
            or type(now) not in (int, float) or not math.isfinite(now) or now < 0
            or not callable(stop_requested)):
        raise ValueError("Invalid private reply boundary")
    try:
        if stop_requested() is not False:
            raise ValueError("Reply cancelled")
    except BaseException as exc:
        raise ValueError("Reply cancelled") from exc
    try:
        record = json.loads(data.decode("utf-8", "strict"),
                            object_pairs_hook=_unique, parse_constant=_no_constant)
    except (UnicodeError, ValueError, RecursionError, OverflowError) as exc:
        raise ValueError("Malformed private reply") from exc
    if type(record) is not dict or set(record) != _REQUIRED:
        raise ValueError("Unexpected response fields")
    try:
        if data != _canonical(record):
            raise ValueError("Noncanonical reply encoding")
    except (UnicodeError, TypeError) as exc:
        raise ValueError("Invalid reply encoding") from exc
    mac = record.pop("mac")
    if type(mac) is not str or _MAC.fullmatch(mac) is None:
        raise ValueError("Bad reply authenticator")
    try:
        body = _body(record["session_id"], record["request_id"],
                     record["issued_at"], record["status"], record["answer"])
    except (ValueError, KeyError, TypeError) as exc:
        raise ValueError("Invalid response structure") from exc
    if (record != body or body["session_id"] != active_session
            or body["request_id"] != expected_request):
        raise ValueError("Response not bound to current request")
    expected = hmac.new(secret, _DOMAIN + _canonical(body),
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, mac):
        raise ValueError("Invalid reply signature")
    delta = now - body["issued_at"]
    if delta > MAX_AGE_SECONDS or delta < -MAX_FUTURE_SKEW_SECONDS:
        raise ValueError("Expired reply")
    try:
        if stop_requested() is not False:
            raise ValueError("Reply cancelled")
    except BaseException as exc:
        raise ValueError("Reply cancelled") from exc
    if not replay_guard.accept_once(body["request_id"]):
        raise ValueError("Duplicate or exhausted reply")
    return ({"status": "ready", "answer": body["answer"]}
            if body["status"] == "ready" else {"status": "withheld"})


def frame_signed_reply(data):
    """Form length-prefixed response bytes; DOES NOT send or open a socket."""
    if type(data) is not bytes or not 0 < len(data) <= MAX_REPLY_BYTES:
        raise ValueError("Invalid framed reply length")
    return _LENGTH.pack(len(data)) + data


def unframe_signed_reply(data):
    """Pure parser for already buffered bytes. No socket or file I/O."""
    if type(data) is not bytes or len(data) < _LENGTH.size:
        raise ValueError("Incomplete reply frame")
    size = _LENGTH.unpack(data[:_LENGTH.size])[0]
    if not 0 < size <= MAX_REPLY_BYTES or len(data) != _LENGTH.size + size:
        raise ValueError("Invalid reply frame")
    return data[_LENGTH.size:]
