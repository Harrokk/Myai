"""Pure preview framing and guarded inspection composition; NO updater service.

The only side effect is a caller-provided **preview-only** SQLite replay
ledger after checks pass. It cannot write project code, sign/release code,
perform recovery, connect/listen sockets or authorize any mutation.
"""

from dataclasses import dataclass
import struct

from core.selfdev_peer_identity import check_preview_peer_socket
from core.selfdev_signed_manifest import verify_signed_inspection_preview
from core.selfdev_request_protocol import compare_supplied_bytes
from core.selfdev_preview_ledger import InspectionReplayLedger


_FRAME_MAX = 40 * 1024


@dataclass(frozen=True)
class OfflinePreviewResult:
    status: str
    request_id: str | None = None
    peer_uid: int | None = None
    signer_key_id: str | None = None
    authorizes_mutation: bool = False
    requires_human_approval: bool = True


def frame_signed_preview(envelope):
    """Return a length-prefixed in-memory message; not network I/O."""
    if type(envelope) is not bytes or not 0 < len(envelope) <= _FRAME_MAX:
        raise ValueError("Invalid inspection frame size.")
    return struct.pack("!I", len(envelope)) + envelope


def unframe_signed_preview(frame):
    """Require EXACTLY one bounded big-endian frame, no trailing payload."""
    if type(frame) is not bytes or not 4 < len(frame) <= _FRAME_MAX + 4:
        raise ValueError("Invalid bounded inspection frame.")
    amount = struct.unpack("!I", frame[:4])[0]
    if not 0 < amount <= _FRAME_MAX or len(frame) != amount + 4:
        raise ValueError("Truncated or concatenated inspection frame.")
    return frame[4:]


def preview_signed_request_offline(
    *,
    connected_unix_socket,
    framed_signed_manifest,
    trusted_runtime_uids,
    updater_uid,
    trusted_public_keys,
    supplied_bytes,
    replay_ledger,
    now_unix,
):
    """Layer kernel peer, signed manifest, file hashes, and replay ledger.

    A successful result says only "preview recorded" and NEVER authorizes
    a source update or privileged IPC. All data files are in-memory,
    except the explicit caller-owned preview-only ledger.
    """
    if type(replay_ledger) is not InspectionReplayLedger:
        raise TypeError("A preview-only replay ledger is required.")
    if type(supplied_bytes) is not dict:
        raise TypeError("Expected in-memory file content map.")
    peer = check_preview_peer_socket(
        connected_unix_socket,
        allowed_runtime_uids=trusted_runtime_uids,
        updater_uid=updater_uid,
    )
    if not peer.accepted_for_preview_only:
        return OfflinePreviewResult(
            status="blocked_untrusted_peer", peer_uid=peer.peer_uid,
        )

    envelope = unframe_signed_preview(framed_signed_manifest)
    signed = verify_signed_inspection_preview(
        envelope, trusted_public_keys, now_unix=now_unix
    )
    checked = compare_supplied_bytes(signed.request, supplied_bytes)
    if checked.status != "bytes_match_untrusted":
        return OfflinePreviewResult(
            status=checked.status,
            request_id=signed.request.request_id,
            peer_uid=peer.peer_uid,
            signer_key_id=signed.signer_key_id,
        )

    claim = replay_ledger.claim(signed.request, now_unix=now_unix)
    return OfflinePreviewResult(
        status=claim.status,
        request_id=signed.request.request_id,
        peer_uid=peer.peer_uid,
        signer_key_id=signed.signer_key_id,
    )
