"""Non-deployment Linux AF_UNIX inspection-only transport boundary.

No server, signer, credentials, key generation, socket creation/bind, process
launch, filesystem path, MyAI runtime or promotion is implemented here.
Client identity is only an OS-issued SO_PEERCRED tuple, never JSON claims.
"""
from __future__ import annotations

import json
import re
import socket
import struct

FRAME_LIMIT = 2048
MAX_TIMEOUT = 5.0
_REQUEST_KEYS = frozenset({"version", "action", "challenge"})
_CHALLENGE = re.compile(r"[0-9a-f]{32}\Z")
_PEER = struct.Struct("3i")
_LENGTH = struct.Struct("!I")


def peer_credentials(connection):
    """Read Linux kernel peer credentials, fail closed on all other platforms."""
    if (not hasattr(socket, "SO_PEERCRED")
            or getattr(connection, "family", None) != socket.AF_UNIX):
        raise PermissionError("Linux Unix socket peer authentication required")
    try:
        raw = connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, _PEER.size)
    except (OSError, AttributeError, TypeError, ValueError) as exc:
        raise PermissionError("Cannot authenticate Unix peer") from exc
    if type(raw) is not bytes or len(raw) != _PEER.size:
        raise PermissionError("Malformed kernel peer credentials")
    pid, uid, gid = _PEER.unpack(raw)
    if pid <= 0 or uid < 0 or gid < 0:
        raise PermissionError("Invalid kernel peer credentials")
    return (pid, uid, gid)


def require_peer_uid(connection, *, expected_uid):
    if type(expected_uid) is not int or expected_uid <= 0:
        raise ValueError("A configured positive service UID is required")
    identity = peer_credentials(connection)
    if identity[1] != expected_uid:
        raise PermissionError("Unauthorized local peer UID")
    return identity


def _require_timeout(connection):
    try:
        timeout = connection.gettimeout()
    except (AttributeError, OSError) as exc:
        raise ValueError("Bounded socket timeout required") from exc
    if (type(timeout) not in (int, float)
            or not 0 < timeout <= MAX_TIMEOUT):
        raise ValueError("Socket must have a strictly bounded timeout")


def receive_frame(connection):
    """Length-prefixed, bounded response with no untrusted memory allocation."""
    _require_timeout(connection)
    def exact(size):
        chunks = bytearray()
        while len(chunks) < size:
            data = connection.recv(size - len(chunks))
            if not data:
                raise ValueError("Truncated IPC frame")
            chunks.extend(data)
        return bytes(chunks)
    size = _LENGTH.unpack(exact(_LENGTH.size))[0]
    if not 0 < size <= FRAME_LIMIT:
        raise ValueError("Unbounded IPC frame")
    return exact(size)


def send_frame(connection, message):
    _require_timeout(connection)
    if type(message) is not bytes or not 0 < len(message) <= FRAME_LIMIT:
        raise ValueError("Invalid outgoing IPC frame")
    connection.sendall(_LENGTH.pack(len(message)) + message)


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate IPC key")
        result[key] = value
    return result


def _reject_nonfinite(value):
    raise ValueError("Nonfinite IPC number")


def parse_inspection_message(message):
    """Never accept passed flags, paths, arbitrary commands or approval tokens."""
    if type(message) is not bytes or not 0 < len(message) <= FRAME_LIMIT:
        raise ValueError("Invalid IPC message size")
    try:
        data = json.loads(
            message.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Malformed inspection IPC message") from exc
    if type(data) is not dict or set(data) != _REQUEST_KEYS:
        raise ValueError("Unexpected fields in inspection IPC request")
    if type(data["version"]) is not int or data["version"] != 1:
        raise ValueError("Unsupported IPC request version")
    if data["action"] != "inspect_fixed_fixture":
        raise ValueError("Mutating or unknown IPC action forbidden")
    if (type(data["challenge"]) is not str
            or _CHALLENGE.fullmatch(data["challenge"]) is None):
        raise ValueError("Invalid updater challenge")
    return data["challenge"]
