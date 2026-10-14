"""Only ephemeral, private Unix sockets: no production server or daemon.

A client connects AFTER fork, allowing SO_PEERCRED to be verified on an
accepted kernel connection instead of on a pre-created socketpair.
"""

from contextlib import contextmanager
import multiprocessing
import os
from pathlib import Path
import socket
import stat

import pytest

from core.selfdev_peer_identity import read_kernel_unix_peer
from core.selfdev_offline_preview_pipeline import frame_signed_preview
from core.selfdev_offline_preview_transport import (
    PreviewTransportError, read_one_preview_frame,
)


pytestmark = pytest.mark.skipif(
    os.name != "posix" or not hasattr(socket, "SO_PEERCRED"),
    reason="Requires Linux SO_PEERCRED and AF_UNIX",
)


@contextmanager
def _one_shot_listener(tmp_path):
    private = tmp_path / "one-shot-preview"
    private.mkdir(mode=0o700)
    path = private / "inspection.sock"
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.bind(str(path))
        path.chmod(0o600)
        listener.listen(1)
        listener.settimeout(2.0)
        try:
            yield listener, path
        finally:
            path.unlink(missing_ok=True)
    assert not path.exists()


def _connect_after_fork(path, wire, send_bytes=True):
    """Executed by a disposable subprocess, not a device service."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(2.0)
        client.connect(str(path))
        if send_bytes:
            client.sendall(wire)
        client.shutdown(socket.SHUT_WR)


def _child_to_new_socket(path, wire, send_bytes=True):
    ctx = multiprocessing.get_context("fork")
    proc = ctx.Process(
        target=_connect_after_fork,
        args=(path, wire, send_bytes),
    )
    proc.start()
    return proc


def _finish_child(child):
    child.join(timeout=3)
    if child.is_alive():
        child.kill()
        child.join(timeout=2)
    assert child.exitcode == 0


def _read(accepted, uid):
    return read_one_preview_frame(
        accepted,
        allowed_runtime_uids=frozenset({uid}),
        updater_uid=uid + 1234,
        timeout_seconds=1.0,
    )


def test_real_accept_peer_pid_is_child_that_connected_after_fork(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("A runtime UID may not be root")
    wire = frame_signed_preview(b"inspection-only")
    with _one_shot_listener(tmp_path) as (listener, path):
        assert stat.S_IMODE(path.lstat().st_mode) == 0o600
        assert stat.S_IMODE(path.parent.lstat().st_mode) == 0o700
        child = _child_to_new_socket(path, wire)
        try:
            with listener.accept()[0] as accepted:
                peer = read_kernel_unix_peer(accepted)
                assert peer.pid == child.pid
                assert peer.uid == os.geteuid()
                assert peer.gid == os.getegid()
                assert _read(accepted, os.geteuid()) == wire
        finally:
            _finish_child(child)
    assert not path.exists()


def test_accepted_socket_rejects_untrusted_uid_without_reading(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("A runtime UID may not be root")
    wire = frame_signed_preview(b'{"claimed_uid":0,"action":"promote"}')
    with _one_shot_listener(tmp_path) as (listener, path):
        child = _child_to_new_socket(path, wire)
        try:
            with listener.accept()[0] as accepted:
                with pytest.raises(PermissionError, match="UID denied"):
                    _read(accepted, os.geteuid() + 100)
                # An unsuccessful identity check must consume no bytes.
                assert _read(accepted, os.geteuid()) == wire
        finally:
            _finish_child(child)


def test_client_disconnect_after_accept_rejects_incomplete_frame(tmp_path):
    if os.geteuid() == 0:
        pytest.skip("A runtime UID may not be root")
    with _one_shot_listener(tmp_path) as (listener, path):
        child = _child_to_new_socket(path, b"\x00\x00", True)
        try:
            with listener.accept()[0] as accepted:
                with pytest.raises(PreviewTransportError, match="incomplete"):
                    _read(accepted, os.geteuid())
        finally:
            _finish_child(child)


def test_accept_deadline_is_bounded_when_no_client_arrives(tmp_path):
    with _one_shot_listener(tmp_path) as (listener, _):
        listener.settimeout(0.05)
        with pytest.raises(socket.timeout):
            listener.accept()


def test_socket_path_does_not_persist_after_one_shot_listener(tmp_path):
    with _one_shot_listener(tmp_path) as (listener, path):
        assert path.is_socket()
        assert listener.fileno() >= 0
    assert not path.exists()
    assert not list(tmp_path.rglob("*.sock"))
