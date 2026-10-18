"""DISPOSABLE DOCKER ONLY: fourth-UID independent Ed25519 observer demo.

Run from the dedicated GitHub-hosted, networkless, temporary Docker workflow.
The verifier executes a fixed synthetic AST inspection in its own subprocess;
it does NOT sign caller-supplied "passed" fields or real MyAI results.
The updater owns the nonce ledger, pins verifier public key delivered via a
test-only root fixture pipe, verifies signature, consumes nonce, blocks replay.
Never start on VENTUNO or use these fake tests as promotion authorization.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import stat
import subprocess
import sys
import tempfile
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_attestation_replay import (
    initialize_ledger, issue_inspection_challenge, consume_signed_inspection,
)
from core.selfdev_signed_evidence import (
    AUDIENCE, ISSUER, canonical_statement_bytes,
)
from core.selfdev_unix_peercred import (
    require_peer_uid, receive_frame, send_frame, parse_inspection_message,
)
import sqlite3


UPDATER = 23001
RUNTIME = 23002
CI = 23003
VERIFIER = 23004
SOURCE = b"SAFE = 1\n"
SOURCE_SHA = hashlib.sha256(SOURCE).hexdigest()
PLAN_SHA = hashlib.sha256(b"myai-disposable-ast-observation/v1").hexdigest()
MANIFEST_SHA = hashlib.sha256(
    b"synthetic-fixture.py:" + SOURCE_SHA.encode("ascii")
).hexdigest()
EVIDENCE_SHA = hashlib.sha256(
    b"MyAI/disposable-observation/v1\n"
    + SOURCE_SHA.encode("ascii") + b"\nexit=0\n"
).hexdigest()
ATTEMPTS = ((CI, "unauthorized"), (RUNTIME, "unauthorized"),
            (UPDATER, "forged"), (UPDATER, "valid"))
_AST_COMMAND = (
    "import ast,hashlib,pathlib,sys;"
    "p=pathlib.Path(sys.argv[1]);"
    "b=p.read_bytes();"
    "ast.parse(b.decode('ascii'),filename='<fixed-fixture>');"
    "print(hashlib.sha256(b).hexdigest())"
)


def disposable_only():
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Container root required")
    if not Path("/.dockerenv").is_file():
        raise RuntimeError("Refusing outside disposable Docker")
    if os.environ.get("MYAI_DISPOSABLE_UID_TEST") != "yes":
        raise RuntimeError("Missing disposable-only execution gate")


def as_uid(uid):
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    assert os.geteuid() == uid


def send_report(fd, record):
    payload = json.dumps(record, sort_keys=True).encode("ascii")
    if len(payload) > 1000:
        raise ValueError("Unbounded report")
    os.write(fd, payload)


def spawn(child, *arguments):
    read_fd, write_fd = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(read_fd)
        try:
            child(*arguments, write_fd)
            os._exit(0)
        except BaseException as error:
            os.write(write_fd, type(error).__name__.encode("ascii", "replace"))
            os._exit(1)
    os.close(write_fd)
    return pid, read_fd


def finish(pid, pipe):
    data = os.read(pipe, 1000)
    os.close(pipe)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError("Isolated test process failed: "
                             + data.decode("ascii", "replace")[:80])
    return json.loads(data)


def independent_observation(private):
    """Never read a passed flag, command, test path or source bytes from IPC."""
    fixture = private / "fixture.py"
    info = fixture.lstat()
    if not stat.S_ISREG(info.st_mode) or info.st_uid != VERIFIER:
        raise PermissionError("Fixed verifier fixture owner/type mismatch")
    if fixture.read_bytes() != SOURCE:
        raise AssertionError("Unexpected fixture content")
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-c", _AST_COMMAND, str(fixture)],
        capture_output=True, text=True, timeout=4, check=False,
        env={"PATH": "/usr/local/bin:/usr/bin:/bin",
             "HOME": "/tmp", "LC_ALL": "C", "PYTHONDONTWRITEBYTECODE": "1"},
    )
    if (result.returncode != 0 or result.stderr
            or result.stdout != SOURCE_SHA + "\n"):
        raise AssertionError("Fixed isolated subprocess observation failed")
    return EVIDENCE_SHA


def verifier(listener, private, public_pipe, report_pipe):
    as_uid(VERIFIER)
    key = Ed25519PrivateKey.generate()
    keyfile = private / "verifier-only-demo-ed25519.key"
    # The private key itself is NEVER serialized to disk; this sentinel file
    # demonstrates dedicated-UID ownership and is not key material.
    with keyfile.open("xb") as stream:
        stream.write(b"not-a-real-private-key")
    os.chmod(keyfile, 0o600)
    public = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    os.write(public_pipe, public)
    os.close(public_pipe)
    accepted = 0
    rejected_uid = 0
    rejected_payload = 0
    for _ in ATTEMPTS:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(3.0)
            try:
                require_peer_uid(connection, expected_uid=UPDATER)
            except PermissionError:
                send_frame(connection, b'{"status":"peer_denied"}')
                rejected_uid += 1
                continue
            try:
                challenge = parse_inspection_message(receive_frame(connection))
            except ValueError:
                send_frame(connection, b'{"status":"request_denied"}')
                rejected_payload += 1
                continue
            result_digest = independent_observation(private)
            now = int(time.time())
            statement = {
                "version": 1, "purpose": "sandbox-verification-only",
                "issuer": ISSUER, "audience": AUDIENCE,
                "session_id": "synthetic_session_1",
                "manifest_sha256": MANIFEST_SHA,
                "test_plan_sha256": PLAN_SHA,
                "evidence_sha256": result_digest,
                "challenge": challenge,
                "verified_unix": now, "expires_unix": now + 60,
                "passed": True, "sandbox": "bubblewrap",
                "network_isolated": True,
                "host_devices_exposed": False,
            }
            # "sandbox": "bubblewrap" here is a synthetic-schema assertion;
            # actual subprocess ran inside a restricted Docker container,
            # NOT Bubblewrap. Therefore THIS ENVELOPE IS NOT REAL EVIDENCE.
            signed = canonical_statement_bytes(statement)
            envelope = json.dumps({
                "statement": statement, "signature": key.sign(signed).hex(),
            }, sort_keys=True, separators=(",", ":")).encode()
            send_frame(connection, envelope)
            accepted += 1
    listener.close()
    send_report(report_pipe, {
        "accepted": accepted, "rejected_uid": rejected_uid,
        "rejected_payload": rejected_payload,
        "private_demo_marker_mode": oct(keyfile.stat().st_mode & 0o777),
    })


def probe(listener, address, private, database, uid, intent, trusted_key, pipe):
    listener.close()
    as_uid(uid)
    try:
        (private / "verifier-only-demo-ed25519.key").read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("Verifier-private marker readable by other UID")
    try:
        (private / "fixture.py").read_bytes()
    except PermissionError:
        pass
    else:
        raise AssertionError("Verifier-owned input readable by another UID")
    if intent == "valid":
        # Database path and nonce are updater-owned; never provided by
        # runtime or CI. Existing test-only code owns its own SQLite file.
        db = sqlite3.connect(database, timeout=2)
        db.execute("PRAGMA synchronous=FULL")
        initialize_ledger(db)
        now = int(time.time())
        issued = issue_inspection_challenge(
            db, session_id="synthetic_session_1",
            manifest_sha256=MANIFEST_SHA,
            test_plan_sha256=PLAN_SHA,
            evidence_sha256=EVIDENCE_SHA,
            now_unix=now, lifetime_seconds=100,
        )
        challenge = issued.challenge
    else:
        db = None
        challenge = "f" * 32
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(3.0)
        client.connect(address)
        request = {
            "version": 1, "action": "inspect_fixed_fixture",
            "challenge": challenge,
        }
        if intent == "forged":
            request["passed"] = True
        if intent != "unauthorized":
            send_frame(client, json.dumps(request, separators=(",", ":")).encode())
        response = receive_frame(client)
    if intent == "unauthorized":
        assert json.loads(response) == {"status": "peer_denied"}
    elif intent == "forged":
        assert json.loads(response) == {"status": "request_denied"}
    else:
        receipt = consume_signed_inspection(
            db, envelope=response,
            trusted_verifier_public_key=trusted_key,
            expected_challenge=challenge, now_unix=int(time.time()),
        )
        assert receipt.signed_context_matched is True
        assert receipt.production_deployment_authorized is False
        assert receipt.independent_verifier_execution_verified is False
        try:
            consume_signed_inspection(
                db, envelope=response,
                trusted_verifier_public_key=trusted_key,
                expected_challenge=challenge, now_unix=int(time.time()),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Replay after successful consumption accepted")
        db.close()
        reopened = sqlite3.connect(database, timeout=2)
        initialize_ledger(reopened)
        try:
            consume_signed_inspection(
                reopened, envelope=response,
                trusted_verifier_public_key=trusted_key,
                expected_challenge=challenge, now_unix=int(time.time()),
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Replay after DB reopen accepted")
        reopened.close()
    send_report(pipe, {"intent": intent, "uid": uid, "result": "correctly_handled"})


def main():
    disposable_only()
    root = Path(tempfile.mkdtemp(prefix="myai-actual-signature-demo-", dir="/tmp"))
    root.chmod(0o755)
    private = root / "verifier"
    private.mkdir()
    fixture = private / "fixture.py"
    fixture.write_bytes(SOURCE)
    os.chown(fixture, VERIFIER, VERIFIER)
    os.chmod(fixture, 0o600)
    os.chown(private, VERIFIER, VERIFIER)
    private.chmod(0o700)
    ledger_dir = root / "updater"
    ledger_dir.mkdir()
    os.chown(ledger_dir, UPDATER, UPDATER)
    ledger_dir.chmod(0o700)
    address = str(root / "verifier.sock")
    database = str(ledger_dir / "challenges.sqlite")

    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as listener:
        listener.settimeout(5.0)
        listener.bind(address)
        os.chmod(address, 0o666)
        listener.listen(4)

        # Test-root transports ONLY the public key from verifier to updater.
        # This is not a production trusted public-key provisioning protocol.
        pubread, pubwrite = os.pipe()
        pid, report_pipe = spawn(verifier, listener, private, pubwrite)
        os.close(pubwrite)
        key = os.read(pubread, 32)
        os.close(pubread)
        assert len(key) == 32
        answers = []
        for uid, intent in ATTEMPTS:
            child, data = spawn(probe, listener, address, private, database,
                                uid, intent, key)
            answers.append(finish(child, data))
        status = finish(pid, report_pipe)
    assert status == {
        "accepted": 1, "rejected_uid": 2, "rejected_payload": 1,
        "private_demo_marker_mode": "0o600",
    }
    assert [x["intent"] for x in answers] == [
        "unauthorized", "unauthorized", "forged", "valid",
    ]
    print(json.dumps({
        "status": "PASS",
        "actual_ed25519_signature_checked": True,
        "fixed_synthetic_ast_subprocess_observed": True,
        "test_only_signature_has_synthetic_bubblewrap_flag": True,
        "all_cross_uid_key_reads_denied": True,
        "unauthorized_peers_rejected": 2,
        "forged_pass_flag_rejected": 1,
        "sqlite_replay_after_reopen_denied": True,
        "real_bubblewrap_evidence_proven": False,
        "production_verifier_service_implemented": False,
        "trusted_public_key_provisioning_proven": False,
        "real_ventuno_runner_or_acl_verified": False,
        "production_deployment_authorized": False,
        "production_touched": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
