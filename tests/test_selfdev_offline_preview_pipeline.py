"""Offline composition tests using only socketpair and temporary SQLite."""

import base64
import hashlib
import json
import os
import socket

import pytest

from core.selfdev_offline_preview_pipeline import (
    frame_signed_preview, unframe_signed_preview, preview_signed_request_offline
)
from core.selfdev_preview_ledger import InspectionReplayLedger
from core.selfdev_signed_manifest import signed_preview_bytes


NOW = 1800000000


def _payload():
    return {
        "version": 1, "action": "inspect_candidate",
        "request_id": "a" * 32, "revision": "b" * 40,
        "expires_unix": NOW + 60,
        "files": [{
            "path": "core/example.py",
            "sha256": hashlib.sha256(b"VALID").hexdigest()
        }],
    }


def _signed(envelope_key="reviewer-a"):
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    signer = Ed25519PrivateKey.generate()  # Ephemeral test-only signing key.
    public = signer.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    manifest = _payload()
    signature = base64.b64encode(
        signer.sign(signed_preview_bytes(key_id=envelope_key, payload=manifest))
    ).decode("ascii")
    envelope = json.dumps({
        "version": 1,
        "algorithm": "Ed25519",
        "key_id": envelope_key,
        "payload": manifest,
        "signature": signature,
    }).encode("utf-8")
    return envelope, {envelope_key: public}


@pytest.mark.parametrize("bad", [
    b"", b"\x00", b"\x00\x00\x00\x00", b"\x00\x00\x00\x10abc",
    b"\x00\x00\x00\x01xy", b"\xff\xff\xff\xffx",
    b"\x00\x00\x00\x01x\x00\x00\x00\x01y",
    b"x" * (40 * 1024 + 5)
])
def test_malformed_framing_fails_closed(bad):
    with pytest.raises(ValueError):
        unframe_signed_preview(bad)


def test_frame_roundtrip_is_unambiguous_and_memory_only():
    message = b'{"test":"preview"}'
    assert unframe_signed_preview(frame_signed_preview(message)) == message
    with pytest.raises(ValueError):
        frame_signed_preview(b"")


def test_wrong_peer_is_rejected_before_signature_or_ledger(tmp_path):
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux Unix credentials required")
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        ledger_path = tmp_path / "preview.db"
        report = preview_signed_request_offline(
            connected_unix_socket=a,
            framed_signed_manifest=b"untrusted",
            trusted_runtime_uids=frozenset({os.geteuid() + 3}),
            updater_uid=os.geteuid() + 4,
            trusted_public_keys={},
            supplied_bytes={},
            replay_ledger=InspectionReplayLedger(ledger_path),
            now_unix=NOW,
        )
        assert report.status == "blocked_untrusted_peer"
        assert report.authorizes_mutation is False
        assert not ledger_path.exists()
    finally:
        a.close()
        b.close()


def test_valid_real_signature_with_kernel_peer_and_replay(tmp_path):
    if not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
        pytest.skip("Requires nonroot Linux SO_PEERCRED")
    envelope, trusted = _signed()
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        ledger = InspectionReplayLedger(tmp_path / "preview.db")
        args = dict(
            connected_unix_socket=a,
            framed_signed_manifest=frame_signed_preview(envelope),
            trusted_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 999,
            trusted_public_keys=trusted,
            supplied_bytes={"core/example.py": b"VALID"},
            replay_ledger=ledger, now_unix=NOW,
        )
        fresh = preview_signed_request_offline(**args)
        assert fresh.status == "recorded_for_inspection"
        assert fresh.peer_uid == os.geteuid()
        assert fresh.signer_key_id == "reviewer-a"
        assert fresh.authorizes_mutation is False
        assert fresh.requires_human_approval is True
        replay = preview_signed_request_offline(**args)
        assert replay.status == "already_seen"
        assert replay.authorizes_mutation is False
    finally:
        a.close()
        b.close()


def test_signature_tamper_is_denied_without_creating_ledger(tmp_path):
    if not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
        pytest.skip("Requires nonroot Linux SO_PEERCRED")
    envelope, trusted = _signed()
    invalid = json.loads(envelope.decode("utf-8"))
    invalid["payload"]["revision"] = "c" * 40
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        ledger_file = tmp_path / "preview.db"
        with pytest.raises(ValueError, match="signature mismatch"):
            preview_signed_request_offline(
                connected_unix_socket=a,
                framed_signed_manifest=frame_signed_preview(
                    json.dumps(invalid).encode("utf-8")
                ),
                trusted_runtime_uids=frozenset({os.geteuid()}),
                updater_uid=os.geteuid() + 999,
                trusted_public_keys=trusted,
                supplied_bytes={"core/example.py": b"VALID"},
                replay_ledger=InspectionReplayLedger(ledger_file),
                now_unix=NOW,
            )
        assert not ledger_file.exists()
    finally:
        a.close()
        b.close()


def test_bad_content_hash_does_not_record_ledger(tmp_path):
    if not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
        pytest.skip("Requires nonroot Linux SO_PEERCRED")
    envelope, trusted = _signed()
    a, b = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        ledger_file = tmp_path / "preview.db"
        result = preview_signed_request_offline(
            connected_unix_socket=a,
            framed_signed_manifest=frame_signed_preview(envelope),
            trusted_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 999,
            trusted_public_keys=trusted,
            supplied_bytes={"core/example.py": b"WRONG"},
            replay_ledger=InspectionReplayLedger(ledger_file),
            now_unix=NOW,
        )
        assert result.status == "blocked_hash_mismatch"
        assert result.authorizes_mutation is False
        assert not ledger_file.exists()
    finally:
        a.close()
        b.close()
