"""OFF-DEVICE Docker-only AF_UNIX SO_PEERCRED integration: no real MyAI.

Four numeric Linux UIDs: updater 23001, runtime 23002, CI 23003,
independent verifier 23004. The verifier independently inspects a fixed,
synthetic local fixture and holds a fresh, dummy HMAC key private to its UID.
This is NOT a production signer, Ed25519 issuer, or real test-run attestation.
"""
from __future__ import annotations

import ast
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import secrets
import socket
import tempfile

UPDATER_UID = 23001
RUNTIME_UID = 23002
CI_UID = 23003
VERIFIER_UID = 23004
NONCE = "a" * 32
EXPECTED = hashlib.sha256(b"SAFE = 1\n").hexdigest()
ATTEMPTS = (
    (CI_UID, "unauthorized"),
    (RUNTIME_UID, "unauthorized"),
    (UPDATER_UID, "invalid"),
    (UPDATER_UID, "valid"),
)


def _require_disposable():
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Disposable container root required")
    if not Path("/.dockerenv").exists():
        raise RuntimeError("Refuse execution outside Docker")
    if os.environ.get("MYAI_DISPOSABLE_UID_TEST") != "yes":
        raise RuntimeError("Explicit Docker test gate required")


def _set_identity(uid):
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    assert os.geteuid() == uid


def _write_pipe(fd, result):
    wire = json.dumps(result, sort_keys=True).encode("ascii")
    if len(wire) > 1024:
        raise RuntimeError("Oversized test reply")
    os.write(fd, wire)


def _read_pipe(fd):
    data = os.read(fd, 1024)
    os.close(fd)
    if not data:
        raise AssertionError("Missing child result")
    return json.loads(data)


def _server(listener, private, response_fd):
    # Import from the separately, read-only mounted policy file.
    from peercred import (
        require_peer_uid, parse_inspection_message, receive_frame, send_frame,
    )
    _set_identity(VERIFIER_UID)
    os.umask(0o077)
    # Fresh secret is created ONLY after the process enters its verifier UID.
    # No CI/runtime/updater child inherits these key bytes from the parent.
    key_path = private / "test-only-mac-key"
    with key_path.open("xb") as stream:
        stream.write(secrets.token_bytes(32))
    os.chmod(key_path, 0o600)
    key = key_path.read_bytes()
    fixture = private / "fixture.py"
    assert fixture.read_bytes() == b"SAFE = 1\n"
    accepted = 0
    denied = 0
    malformed = 0
    for _ in ATTEMPTS:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(3.0)
            try:
                require_peer_uid(connection, expected_uid=UPDATER_UID)
            except PermissionError:
                send_frame(connection, b'{"status":"peer_denied"}')
                denied += 1
                continue
            try:
                challenge = parse_inspection_message(receive_frame(connection))
            except ValueError:
                send_frame(connection, b'{"status":"request_denied"}')
                malformed += 1
                continue
            # Peer claims nothing about results, paths or commands. Independently
            # parse the verifier-owned fixture and check its pinned expected hash.
            source = fixture.read_bytes()
            ast.parse(source.decode("ascii"), filename="<synthetic>")
            digest = hashlib.sha256(source).hexdigest()
            if digest != EXPECTED:
                raise AssertionError("Verifier-owned fixed fixture changed")
            # Dummy MAC demonstrates that only verifier UID can read its key.
            # Not Ed25519 and NOT an authorization or signature of real tests.
            mac = hmac.new(
                key, b"MyAI/disposable-fixture-test/v1\0"
                + challenge.encode("ascii") + bytes.fromhex(digest),
                hashlib.sha256,
            ).hexdigest()
            send_frame(connection, json.dumps({
                "status": "inspected_only",
                "fixture_sha256": digest,
                "challenge": challenge,
                "dummy_mac": mac,
                "authorizes_mutation": False,
            }, sort_keys=True).encode("ascii"))
            accepted += 1
    listener.close()
    _write_pipe(response_fd, {
        "role": "verifier", "accepted": accepted,
        "denied": denied, "malformed": malformed,
        "private_key_mode": oct(key_path.stat().st_mode & 0o777),
    })


def _client(listener, address, private, uid, intent, response_fd):
    from peercred import receive_frame, send_frame
    listener.close()
    _set_identity(uid)
    # Non-verifier UIDs cannot access key OR synthetic independent evidence.
    try:
        (private / "test-only-mac-key").read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("Private key readable outside verifier UID")
    try:
        (private / "fixture.py").read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("Verifier-only fixture readable by caller")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3.0)
        client.connect(address)
        data = {
            "version": 1,
            "action": "inspect_fixed_fixture",
            "challenge": NONCE,
        }
        if intent == "invalid":
            data["passed"] = True  # Untrusted status claims MUST be rejected.
        send_frame(client, json.dumps(data, separators=(",", ":")).encode())
        response = json.loads(receive_frame(client))
    expected = {
        "unauthorized": "peer_denied",
        "invalid": "request_denied",
        "valid": "inspected_only",
    }[intent]
    assert response.get("status") == expected
    if intent == "valid":
        assert response["fixture_sha256"] == EXPECTED
        assert response["challenge"] == NONCE
        assert re.fullmatch("[0-9a-f]{64}", response["dummy_mac"])
        assert response["authorizes_mutation"] is False
    else:
        assert "dummy_mac" not in response
    _write_pipe(response_fd, {"role": intent, "uid": uid, "expected": expected})


def _child(fn, *args):
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            fn(*args, writer)
            os._exit(0)
        except BaseException as exc:
            os.write(writer, type(exc).__name__.encode("ascii", "replace"))
            os._exit(1)
    os.close(writer)
    return pid, reader


def _wait_child(pid, reader):
    answer = os.read(reader, 1024)
    os.close(reader)
    _, code = os.waitpid(pid, 0)
    if not os.WIFEXITED(code) or os.WEXITSTATUS(code) != 0:
        raise AssertionError("Disposable child failed: "
                             + answer.decode("ascii", "replace")[:64])
    return json.loads(answer)


def main():
    _require_disposable()
    root = Path(tempfile.mkdtemp(prefix="myai-verifier-ipc-", dir="/tmp"))
    root.chmod(0o755)
    private = root / "verifier-private"
    private.mkdir()
    fixture = private / "fixture.py"
    fixture.write_bytes(b"SAFE = 1\n")
    os.chown(fixture, VERIFIER_UID, VERIFIER_UID)
    os.chmod(fixture, 0o600)
    os.chown(private, VERIFIER_UID, VERIFIER_UID)
    private.chmod(0o700)

    address = str(root / "verifier.sock")
    # Socket availability is NOT authorization: all UIDs may connect,
    # but only the kernel-reported updater UID can submit a request.
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.settimeout(5.0)
        listener.bind(address)
        os.chmod(address, 0o666)
        listener.listen(4)
        server_pid, server_reader = _child(_server, listener, private)
        responses = []
        for uid, intent in ATTEMPTS:
            pid, reader = _child(_client, listener, address, private, uid, intent)
            responses.append(_wait_child(pid, reader))
        server = _wait_child(server_pid, server_reader)
    assert server == {
        "role": "verifier", "accepted": 1, "denied": 2,
        "malformed": 1, "private_key_mode": "0o600",
    }
    assert [x["expected"] for x in responses] == [
        "peer_denied", "peer_denied", "request_denied", "inspected_only",
    ]
    print(json.dumps({
        "status": "PASS",
        "isolated_linux_uids": 4,
        "unauthorized_peers_rejected": 2,
        "fake_pass_flags_rejected": 1,
        "independent_fixed_fixture_inspected": True,
        "dummy_key_unreadable_by_other_uids": True,
        "ed25519_verifier_service_implemented": False,
        "independent_production_verification_proven": False,
        "physical_hardware_tests_authorized": False,
        "production_deployment_authorized": False,
        "production_touched": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
