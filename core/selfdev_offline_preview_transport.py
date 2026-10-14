"""Bounded read from an ALREADY CONNECTED offline AF_UNIX stream.

No bind, listen, accept, connect, send, filesystem or service actions.
The sender must shutdown(SHUT_WR) after exactly one length-prefixed request.
All reads share one monotonic deadline; failure NEVER authorizes mutation.
"""

import math
import select
import socket
import struct
import time

from core.selfdev_peer_identity import check_preview_peer_socket
from core.selfdev_offline_preview_pipeline import (
    _FRAME_MAX,
    preview_signed_request_offline,
)


_MAX_DEADLINE_SECONDS = 5.0


class PreviewTransportError(ValueError):
    """Invalid, incomplete, or unexpected message transport behavior."""


def _read_ready_chunk(sock, amount, deadline):
    """Do not alter caller socket blocking mode and never wait indefinitely."""
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Inspection message deadline exceeded.")
        try:
            ready, _, _ = select.select([sock], [], [], remaining)
        except InterruptedError:
            continue
        except (OSError, ValueError) as error:
            raise PreviewTransportError("Inspection socket is unavailable.") from error
        if not ready:
            raise TimeoutError("Inspection message deadline exceeded.")
        try:
            return sock.recv(amount, socket.MSG_DONTWAIT)
        except (InterruptedError, BlockingIOError):
            continue
        except OSError as error:
            raise PreviewTransportError("Inspection socket read failed.") from error


def _receive_exact(sock, amount, deadline):
    result = bytearray()
    while len(result) < amount:
        part = _read_ready_chunk(sock, amount - len(result), deadline)
        if not part:
            raise PreviewTransportError("Inspection peer closed an incomplete frame.")
        result.extend(part)
    return bytes(result)


def read_one_preview_frame(
    connected_unix_socket,
    *,
    allowed_runtime_uids,
    updater_uid,
    timeout_seconds=1.0,
):
    """Validate kernel UID first; read ONE frame and REQUIRE writer-side EOF.

    Requiring EOF makes a delayed second frame or trailing bytes a failure.
    A sender can still receive a future reply after shutdown(SHUT_WR); this
    prototype does not implement sending a reply or a server transport.
    """
    if (
        type(timeout_seconds) not in (int, float)
        or not math.isfinite(timeout_seconds)
        or not 0 < timeout_seconds <= _MAX_DEADLINE_SECONDS
    ):
        raise ValueError("Invalid finite inspection deadline.")
    if not hasattr(socket, "MSG_DONTWAIT"):
        raise RuntimeError("Nonblocking Unix socket reads unsupported.")
    peer = check_preview_peer_socket(
        connected_unix_socket,
        allowed_runtime_uids=allowed_runtime_uids,
        updater_uid=updater_uid,
    )
    if not peer.accepted_for_preview_only:
        raise PermissionError("Inspection peer UID denied before reading bytes.")

    # One deadline, including header, payload and the final peer EOF.
    deadline = time.monotonic() + timeout_seconds
    header = _receive_exact(connected_unix_socket, 4, deadline)
    amount = struct.unpack("!I", header)[0]
    if not 0 < amount <= _FRAME_MAX:
        raise PreviewTransportError("Declared inspection frame size is invalid.")
    payload = _receive_exact(connected_unix_socket, amount, deadline)
    trailing = _read_ready_chunk(connected_unix_socket, 1, deadline)
    if trailing:
        raise PreviewTransportError("Inspection peer sent trailing data.")
    return header + payload


def preview_signed_request_from_connected_socket_offline(
    *,
    connected_unix_socket,
    trusted_runtime_uids,
    updater_uid,
    trusted_public_keys,
    supplied_bytes,
    replay_ledger,
    now_unix,
    timeout_seconds=1.0,
):
    """Receive once then pass immutable bytes through the PREVIEW-only chain."""
    framed = read_one_preview_frame(
        connected_unix_socket,
        allowed_runtime_uids=trusted_runtime_uids,
        updater_uid=updater_uid,
        timeout_seconds=timeout_seconds,
    )
    return preview_signed_request_offline(
        connected_unix_socket=connected_unix_socket,
        framed_signed_manifest=framed,
        trusted_runtime_uids=trusted_runtime_uids,
        updater_uid=updater_uid,
        trusted_public_keys=trusted_public_keys,
        supplied_bytes=supplied_bytes,
        replay_ledger=replay_ledger,
        now_unix=now_unix,
    )
