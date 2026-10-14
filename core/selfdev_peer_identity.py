"""Read-only Unix peer identity check for a future inspection socket.

DOES NOT create/listen/connect, authenticate a release, sign, deploy, update,
or interact with a production selfdev service. Source of UID is kernel
SO_PEERCRED on an already-connected AF_UNIX stream socket, NEVER JSON.
"""

from dataclasses import dataclass
import os
import socket
import struct


@dataclass(frozen=True)
class KernelPeer:
    pid: int
    uid: int
    gid: int


@dataclass(frozen=True)
class InspectionPeerDecision:
    status: str
    peer_uid: int | None
    accepted_for_preview_only: bool
    authorizes_mutation: bool = False
    requires_human_approval: bool = True


def read_kernel_unix_peer(sock):
    """Read Linux SO_PEERCRED, never a self-asserted UID in a message."""
    if not isinstance(sock, socket.socket):
        raise TypeError("A real connected socket object is required.")
    if sock.family != socket.AF_UNIX or (
        (sock.type & 0xf) != socket.SOCK_STREAM
    ):
        raise PermissionError("Only connected AF_UNIX streams are supported.")
    if not hasattr(socket, "SO_PEERCRED"):
        raise RuntimeError("Kernel peer credentials unavailable: fail closed.")
    try:
        sock.getpeername()  # Requires a connected socket.
        packed = sock.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")
        )
    except OSError as error:
        raise PermissionError("Kernel Unix peer credentials unavailable.") from error
    if len(packed) != struct.calcsize("3i"):
        raise PermissionError("Unexpected Unix peer credential length.")
    pid, uid, gid = struct.unpack("3i", packed)
    if pid <= 0 or uid < 0 or gid < 0:
        raise PermissionError("Invalid kernel peer credentials.")
    return KernelPeer(pid=pid, uid=uid, gid=gid)


def check_preview_peer_socket(sock, *, allowed_runtime_uids, updater_uid):
    """Check a kernel UID against out-of-band configuration for PREVIEW only.

    Passing this policy NEVER creates approval to mutate. Runtime roles must
    be distinct from the updater, and root cannot submit runtime previews.
    """
    if (
        type(allowed_runtime_uids) is not frozenset
        or not allowed_runtime_uids
        or any(type(uid) is not int or uid <= 0 for uid in allowed_runtime_uids)
        or type(updater_uid) is not int
        or updater_uid <= 0
        or updater_uid in allowed_runtime_uids
    ):
        raise ValueError("Unsafe updater/runtime identity policy.")
    peer = read_kernel_unix_peer(sock)
    if peer.uid not in allowed_runtime_uids:
        return InspectionPeerDecision(
            status="blocked_untrusted_runtime_uid",
            peer_uid=peer.uid,
            accepted_for_preview_only=False,
        )
    if peer.uid == updater_uid or peer.uid == 0:
        return InspectionPeerDecision(
            status="blocked_privileged_peer",
            peer_uid=peer.uid,
            accepted_for_preview_only=False,
        )
    return InspectionPeerDecision(
        status="allowed_preview_transport_identity_only",
        peer_uid=peer.uid,
        accepted_for_preview_only=True,
    )
