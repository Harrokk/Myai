"""Pure unit regression of Linux-only peer-authenticated non-promoting IPC."""
import json
import socket
import struct
from pathlib import Path
from types import SimpleNamespace

import pytest

from core import selfdev_unix_peercred as p

ROOT = Path(__file__).resolve().parents[1]


class FakeSocket:
    family = socket.AF_UNIX
    def __init__(self, *, uid=23001, pid=444, gid=23001,
                 timeout=3.0, input_bytes=b""):
        self.creds = struct.pack("3i", pid, uid, gid)
        self.timeout = timeout
        self.input = bytearray(input_bytes)
        self.output = bytearray()
    def getsockopt(self, level, opt, size):
        assert level == socket.SOL_SOCKET
        assert opt == socket.SO_PEERCRED
        assert size == 12
        return self.creds
    def gettimeout(self):
        return self.timeout
    def recv(self, n):
        part = bytes(self.input[:min(n, 2)])
        del self.input[:len(part)]
        return part
    def sendall(self, data):
        self.output.extend(data)


def request(**overrides):
    obj = {"version": 1, "action": "inspect_fixed_fixture",
           "challenge": "a" * 32}
    obj.update(overrides)
    return json.dumps(obj, separators=(",", ":")).encode()


@pytest.mark.skipif(not hasattr(socket, "SO_PEERCRED"), reason="Linux only")
def test_kernel_provided_identity_not_json_claim():
    sock = FakeSocket()
    assert p.require_peer_uid(sock, expected_uid=23001) == (444, 23001, 23001)
    with pytest.raises(PermissionError, match="Unauthorized"):
        p.require_peer_uid(FakeSocket(uid=23002), expected_uid=23001)
    with pytest.raises(PermissionError):
        p.require_peer_uid(FakeSocket(uid=23003), expected_uid=23001)


@pytest.mark.parametrize("wrong", [0, -1, True, 23001.0, "23001", None])
def test_expected_service_uid_must_be_pinned_positive_int(wrong):
    with pytest.raises(ValueError):
        p.require_peer_uid(FakeSocket(), expected_uid=wrong)


def test_peercred_rejects_non_linux_or_non_unix_clients(monkeypatch):
    sock = FakeSocket()
    sock.family = socket.AF_INET
    with pytest.raises(PermissionError):
        p.peer_credentials(sock)
    sock.family = socket.AF_UNIX
    sock.creds = b"short"
    with pytest.raises(PermissionError):
        p.peer_credentials(sock)


@pytest.mark.parametrize("bad", [
    b"", b"{}", b"[]", b"null", b"\xff",
    b'{"version":1,"version":1,"action":"inspect_fixed_fixture","challenge":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
    b'{"version":NaN,"action":"inspect_fixed_fixture","challenge":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"}',
    b"x" * 2049,
])
def test_malformed_duplicate_nonfinite_oversized_requests_rejected(bad):
    with pytest.raises(ValueError):
        p.parse_inspection_message(bad)


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 2}, {"version": 1.0},
    {"action": "sign_passed"}, {"action": "promote"},
    {"action": "restart"}, {"action": "inspect_fixed_fixture;promote"},
    {"challenge": "A" * 32}, {"challenge": "a" * 31},
    {"challenge": 123}, {"passed": True}, {"command": "touch /tmp/unsafe"},
    {"path": "/etc/passwd"}, {"approval": True}, {"source_bytes": "x"},
    {"private_key": "abc"}, {"requester_uid": 23001},
])
def test_untrusted_commands_results_paths_or_identity_claims_denied(patch):
    with pytest.raises(ValueError):
        p.parse_inspection_message(request(**patch))


def test_minimal_inspection_only_challenge_is_accepted():
    assert p.parse_inspection_message(request()) == "a" * 32


def test_bounded_framing_success_even_with_fragmented_receives():
    wire = request()
    data = struct.pack("!I", len(wire)) + wire
    sock = FakeSocket(input_bytes=data)
    assert p.receive_frame(sock) == wire
    p.send_frame(sock, wire)
    assert bytes(sock.output) == data


@pytest.mark.parametrize("bad", [
    b"\x00\x00\x00\x00", b"\x00\x01\x00\x00",
    b"\x00\x00\x00\x20incomplete",
    b"\x00",
])
def test_truncated_unbounded_and_zero_length_frames_denied(bad):
    with pytest.raises(ValueError):
        p.receive_frame(FakeSocket(input_bytes=bad))


@pytest.mark.parametrize("timeout", [None, 0, -1, 6.0, True, "3"])
def test_unspecified_or_unbounded_socket_timeout_rejected(timeout):
    with pytest.raises(ValueError):
        p.receive_frame(FakeSocket(input_bytes=b"123", timeout=timeout))
    with pytest.raises(ValueError):
        p.send_frame(FakeSocket(timeout=timeout), b"x")


def test_outgoing_frame_limit():
    with pytest.raises(ValueError):
        p.send_frame(FakeSocket(), b"x" * 2049)


def test_workflow_is_host_only_with_single_inspection_test_script_and_policy():
    content = (ROOT / ".github/workflows/disposable-verifier-peercred-ipc.yml").read_text()
    assert "runs-on: ubuntu-24.04" in content
    assert "runs-on: [self-hosted" not in content
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in content
    assert "RUNNER_ENVIRONMENT: " + "${{ runner.environment }}" in content
    assert "permissions:\n  contents: read" in content
    assert "docker run --rm --network none --read-only" in content
    assert "--cap-drop ALL" in content
    assert "--security-opt no-new-privileges" in content
    assert "sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258" in content
    assert content.count("type=bind") == 2
    assert "dst=/opt/peercred.py,readonly" in content
    assert "dst=/opt/ipc-test.py,readonly" in content
    assert "workflow_dispatch:" not in content
    assert "secrets." not in content
    assert "systemctl" not in content
    assert "/home/arduino/" not in content
    assert "rev-parse HEAD" in content
    assert '"$GITHUB_SHA"' in content


def test_fixture_starts_only_in_disposable_container_and_never_grants_promotion():
    content = (ROOT / "scripts/test_disposable_verifier_peercred_ipc.py").read_text()
    assert 'if __name__ == "__main__":' in content
    assert "os.environ.get(\"MYAI_DISPOSABLE_UID_TEST\")" in content
    assert "os.setgroups([])" in content
    assert "os.setuid(uid)" in content
    assert 'nonce_factory' not in content
    assert '"ed25519_verifier_service_implemented": False' in content
    assert '"production_deployment_authorized": False' in content
    assert '"production_touched": False' in content


def test_transport_policy_does_not_generate_signatures_or_call_promotion():
    source = (ROOT / "core/selfdev_unix_peercred.py").read_text()
    for forbidden in ("Ed25519PrivateKey", "SelfDevPromotionManager",
                      "subprocess.", "systemctl", "sqlite3.connect"):
        assert forbidden not in source
