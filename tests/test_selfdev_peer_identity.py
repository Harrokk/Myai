"""AF_UNIX peer credential tests; no listener or production socket."""

import os
import socket

import pytest

from core.selfdev_peer_identity import (
    read_kernel_unix_peer, check_preview_peer_socket,
)


@pytest.fixture
def unix_pair():
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("Linux kernel SO_PEERCRED required")
    first, second = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        yield first, second
    finally:
        first.close()
        second.close()


def test_unix_socketpair_reads_real_kernel_identity(unix_pair):
    first, _ = unix_pair
    peer = read_kernel_unix_peer(first)
    assert peer.uid == os.geteuid()
    assert peer.gid == os.getegid()
    assert peer.pid == os.getpid()


def test_allowed_runtime_uid_still_never_authorizes_mutation(unix_pair):
    if os.geteuid() == 0:
        pytest.skip("Test runner is root; runtime intentionally refuses root")
    first, _ = unix_pair
    report = check_preview_peer_socket(
        first, allowed_runtime_uids=frozenset({os.geteuid()}),
        updater_uid=os.geteuid() + 1234,
    )
    assert report.status == "allowed_preview_transport_identity_only"
    assert report.accepted_for_preview_only is True
    assert report.authorizes_mutation is False
    assert report.requires_human_approval is True


def test_wrong_runtime_uid_is_blocked_even_with_valid_socket(unix_pair):
    first, _ = unix_pair
    report = check_preview_peer_socket(
        first, allowed_runtime_uids=frozenset({os.geteuid() + 3}),
        updater_uid=os.geteuid() + 4,
    )
    assert report.status == "blocked_untrusted_runtime_uid"
    assert report.accepted_for_preview_only is False
    assert report.authorizes_mutation is False


@pytest.mark.parametrize("allowed,updater", [
    (frozenset(), 2000),
    (frozenset({1000}), 1000),
    (frozenset({0}), 2000),
    (frozenset({True}), 2000),
    ({1000}, 2000),
    (frozenset({1000}), 0),
    (frozenset({1000}), True),
    (frozenset({-1}), 2000),
])
def test_broken_privilege_policy_is_rejected(unix_pair, allowed, updater):
    first, _ = unix_pair
    with pytest.raises(ValueError, match="identity policy"):
        check_preview_peer_socket(
            first, allowed_runtime_uids=allowed, updater_uid=updater
        )


def test_unconnected_unix_socket_cannot_claim_kernel_identity():
    if not hasattr(socket, "SO_PEERCRED"):
        pytest.skip("SO_PEERCRED required")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        with pytest.raises(PermissionError):
            read_kernel_unix_peer(client)


def test_ipv4_socket_is_rejected_without_network_traffic():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
        with pytest.raises(PermissionError, match="AF_UNIX"):
            read_kernel_unix_peer(client)


def test_self_reported_credentials_dictionary_is_not_accepted():
    with pytest.raises(TypeError, match="real connected socket"):
        read_kernel_unix_peer({"uid": os.geteuid(), "gid": os.getegid()})


def test_closing_socket_prevents_later_peer_authentication(unix_pair):
    first, _ = unix_pair
    first.close()
    with pytest.raises(PermissionError):
        read_kernel_unix_peer(first)
