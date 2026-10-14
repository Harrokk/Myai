"""Socketpair-only transport tests: no listener, bind or production service."""

import base64
import hashlib
import json
import math
import os
import socket
import struct
import threading
import time

import pytest

from core.selfdev_offline_preview_pipeline import frame_signed_preview
from core.selfdev_offline_preview_transport import (
    PreviewTransportError,
    read_one_preview_frame,
    preview_signed_request_from_connected_socket_offline,
)
from core.selfdev_preview_ledger import InspectionReplayLedger
from core.selfdev_signed_manifest import signed_preview_bytes


NOW = 1800000000


@pytest.fixture
def pair():
    if not hasattr(socket, "SO_PEERCRED") or os.geteuid() == 0:
        pytest.skip("Requires nonroot Linux kernel peer credentials")
    receiver, sender = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        yield receiver, sender
    finally:
        receiver.close()
        sender.close()


def _receive(receiver, **kwargs):
    return read_one_preview_frame(
        receiver,
        allowed_runtime_uids=frozenset({os.geteuid()}),
        updater_uid=os.geteuid() + 1000,
        timeout_seconds=0.5,
        **kwargs,
    )


def _send_fragments(sender, fragments, delay=0.002):
    for part in fragments:
        sender.sendall(part)
        time.sleep(delay)
    sender.shutdown(socket.SHUT_WR)


def test_split_header_and_payload_can_be_received_without_blocking(pair):
    receiver, sender = pair
    wire = frame_signed_preview(b"payload-with-multiple-fragments")
    producer = threading.Thread(
        target=_send_fragments,
        args=(sender, [wire[:1], wire[1:3], wire[3:4], wire[4:8], wire[8:]]),
    )
    producer.start()
    try:
        assert _receive(receiver) == wire
    finally:
        producer.join(timeout=2)
    assert not producer.is_alive()


def test_single_complete_frame_and_writer_halfclose(pair):
    receiver, sender = pair
    wire = frame_signed_preview(b"valid")
    sender.sendall(wire)
    sender.shutdown(socket.SHUT_WR)
    assert _receive(receiver) == wire


@pytest.mark.parametrize("partial", [
    b"", b"\x00", b"\x00\x00\x00", b"\x00\x00\x00\x05hi",
    b"\x00\x00\x00\x01",
])
def test_early_eof_never_accepts_partial_frame(pair, partial):
    receiver, sender = pair
    if partial:
        sender.sendall(partial)
    sender.shutdown(socket.SHUT_WR)
    with pytest.raises(PreviewTransportError, match="incomplete"):
        _receive(receiver)


@pytest.mark.parametrize("size", [0, 40 * 1024 + 1, 2**32 - 1])
def test_oversized_or_empty_advertised_payload_denied_immediately(pair, size):
    receiver, sender = pair
    sender.sendall(struct.pack("!I", size))
    with pytest.raises(PreviewTransportError, match="size"):
        _receive(receiver)


def test_extra_frame_is_rejected(pair):
    receiver, sender = pair
    sender.sendall(frame_signed_preview(b"one") + frame_signed_preview(b"two"))
    sender.shutdown(socket.SHUT_WR)
    with pytest.raises(PreviewTransportError, match="trailing"):
        _receive(receiver)


def test_delayed_trailing_bytes_are_rejected_before_peer_eof(pair):
    receiver, sender = pair
    wire = frame_signed_preview(b"one")
    producer = threading.Thread(
        target=_send_fragments,
        args=(sender, [wire, b"late-unauthorized-data"], 0.03),
    )
    producer.start()
    try:
        with pytest.raises(PreviewTransportError, match="trailing"):
            _receive(receiver)
    finally:
        producer.join(timeout=2)
    assert not producer.is_alive()


def test_payload_without_writer_halfclose_times_out(pair):
    receiver, sender = pair
    sender.sendall(frame_signed_preview(b"complete-but-connection-open"))
    with pytest.raises(TimeoutError, match="deadline"):
        read_one_preview_frame(
            receiver,
            allowed_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 1000,
            timeout_seconds=0.05,
        )


@pytest.mark.parametrize("timeout", [
    0, -1, 5.0001, 100, float("nan"), float("inf"), "1", True,
])
def test_invalid_timeout_rejected_before_socket_read(pair, timeout):
    receiver, _ = pair
    with pytest.raises(ValueError, match="deadline"):
        read_one_preview_frame(
            receiver,
            allowed_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 1000,
            timeout_seconds=timeout,
        )


def test_untrusted_peer_is_rejected_without_consuming_any_data(pair):
    receiver, sender = pair
    wire = frame_signed_preview(b"not-for-this-identity")
    sender.sendall(wire)
    sender.shutdown(socket.SHUT_WR)
    with pytest.raises(PermissionError, match="UID denied"):
        read_one_preview_frame(
            receiver,
            allowed_runtime_uids=frozenset({os.geteuid() + 200}),
            updater_uid=os.geteuid() + 300,
        )
    assert _receive(receiver) == wire


def test_idle_peer_times_out_without_creating_any_files(tmp_path, pair):
    receiver, _ = pair
    before = list(tmp_path.iterdir())
    with pytest.raises(TimeoutError, match="deadline"):
        read_one_preview_frame(
            receiver,
            allowed_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 1000,
            timeout_seconds=0.05,
        )
    assert list(tmp_path.iterdir()) == before


def test_closed_socket_denied_without_side_effects(pair):
    receiver, _ = pair
    receiver.close()
    with pytest.raises(PermissionError):
        _receive(receiver)


def _signed():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    secret = Ed25519PrivateKey.generate()
    key = secret.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    manifest = {
        "version": 1, "action": "inspect_candidate",
        "request_id": "a" * 32, "revision": "b" * 40,
        "expires_unix": NOW + 60,
        "files": [{
            "path": "core/example.py",
            "sha256": hashlib.sha256(b"VALUE").hexdigest(),
        }],
    }
    signature = base64.b64encode(
        secret.sign(signed_preview_bytes(key_id="offline-a", payload=manifest))
    ).decode("ascii")
    return json.dumps({
        "version": 1, "algorithm": "Ed25519",
        "key_id": "offline-a", "payload": manifest,
        "signature": signature,
    }).encode("utf-8"), {"offline-a": key}


def test_real_signed_transport_then_replay_remains_preview_only(tmp_path, pair):
    receiver, sender = pair
    envelope, trusted = _signed()
    sender.sendall(frame_signed_preview(envelope))
    sender.shutdown(socket.SHUT_WR)
    report = preview_signed_request_from_connected_socket_offline(
        connected_unix_socket=receiver,
        trusted_runtime_uids=frozenset({os.geteuid()}),
        updater_uid=os.geteuid() + 1000,
        trusted_public_keys=trusted,
        supplied_bytes={"core/example.py": b"VALUE"},
        replay_ledger=InspectionReplayLedger(tmp_path / "preview.db"),
        now_unix=NOW,
    )
    assert report.status == "recorded_for_inspection"
    assert report.authorizes_mutation is False
    assert report.requires_human_approval is True


def test_truncated_signed_transport_does_not_record_preview(tmp_path, pair):
    receiver, sender = pair
    envelope, trusted = _signed()
    wire = frame_signed_preview(envelope)
    sender.sendall(wire[:-10])
    sender.shutdown(socket.SHUT_WR)
    path = tmp_path / "preview.db"
    with pytest.raises(PreviewTransportError, match="incomplete"):
        preview_signed_request_from_connected_socket_offline(
            connected_unix_socket=receiver,
            trusted_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 1000,
            trusted_public_keys=trusted,
            supplied_bytes={"core/example.py": b"VALUE"},
            replay_ledger=InspectionReplayLedger(path),
            now_unix=NOW,
        )
    assert not path.exists()



def _slow_fragment_writer(sender, chunks, delay):
    """Avoid accumulating thread errors when the receiver times out."""
    try:
        for part in chunks:
            sender.sendall(part)
            time.sleep(delay)
        sender.shutdown(socket.SHUT_WR)
    except (BrokenPipeError, ConnectionResetError, OSError):
        pass


def test_many_slow_fragments_cannot_reset_global_deadline(pair):
    receiver, sender = pair
    wire = frame_signed_preview(b"abcdefghijklmno")
    producer = threading.Thread(
        target=_slow_fragment_writer,
        args=(sender, [wire[i:i + 1] for i in range(len(wire))], 0.035),
    )
    producer.start()
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="deadline"):
            read_one_preview_frame(
                receiver,
                allowed_runtime_uids=frozenset({os.geteuid()}),
                updater_uid=os.geteuid() + 200,
                timeout_seconds=0.10,
            )
        assert time.monotonic() - started < 0.6
    finally:
        producer.join(timeout=2)
    assert not producer.is_alive()


def test_socket_blocking_and_timeout_settings_are_never_mutated(pair):
    receiver, sender = pair
    receiver.settimeout(1.25)
    prior_timeout = receiver.gettimeout()
    wire = frame_signed_preview(b"complete")
    sender.sendall(wire)
    sender.shutdown(socket.SHUT_WR)
    assert _receive(receiver) == wire
    assert receiver.gettimeout() == prior_timeout


def test_timeout_preserves_nonblocking_socket_flag(pair):
    receiver, _ = pair
    receiver.setblocking(False)
    assert receiver.gettimeout() == 0.0
    with pytest.raises(TimeoutError, match="deadline"):
        read_one_preview_frame(
            receiver,
            allowed_runtime_uids=frozenset({os.geteuid()}),
            updater_uid=os.geteuid() + 200,
            timeout_seconds=0.05,
        )
    assert receiver.gettimeout() == 0.0


def test_receiver_socket_closed_between_fragments_fails_closed(pair, monkeypatch):
    from core import selfdev_offline_preview_transport as module
    receiver, sender = pair
    wire = frame_signed_preview(b"something")
    sender.sendall(wire)
    sender.shutdown(socket.SHUT_WR)
    existing = module._read_ready_chunk
    reads = [0]

    def close_after_first_recv(sock, amount, deadline):
        data = existing(sock, amount, deadline)
        reads[0] += 1
        if reads[0] == 1:
            sock.close()
        return data

    monkeypatch.setattr(module, "_read_ready_chunk", close_after_first_recv)
    with pytest.raises(PreviewTransportError, match="unavailable"):
        _receive(receiver)
