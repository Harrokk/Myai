"""DISPOSABLE GITHUB-HOSTED LINUX ONLY: FOUR-UID REAL Bubblewrap Ed25519 test.

Run from the dedicated disposable GitHub-hosted Ubuntu host workflow.
The verifier runs real network-unshared Bubblewrap after changing UID;
it does NOT sign caller-supplied "passed" fields or real MyAI results.
The updater owns the nonce ledger, pins verifier public key delivered via a
test-only root fixture pipe, verifies signature, consumes nonce, blocks replay.
Never start on VENTUNO or use these test-only keys as promotion authorization.
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
from core.selfdev_bwrap_observation import (
    FIXTURE, FIXTURE_SHA256, PLAN_SHA256, observe,
)


UPDATER = 23001
RUNTIME = 23002
CI = 23003
VERIFIER = 23004
SOURCE = FIXTURE
SOURCE_SHA = FIXTURE_SHA256
PLAN_SHA = PLAN_SHA256
MANIFEST_SHA = hashlib.sha256(
    b"fixture.py:" + SOURCE_SHA.encode("ascii")
).hexdigest()
EVIDENCE_SHA = hashlib.sha256(
    b"MyAI/disposable-real-bwrap-observation/v1\0"
    + bytes.fromhex(SOURCE_SHA) + bytes.fromhex(PLAN_SHA)
).hexdigest()
ATTEMPTS = ((CI, "unauthorized"), (RUNTIME, "unauthorized"),
            (UPDATER, "forged"), (UPDATER, "valid"))

def disposable_only():
    if os.name != "posix" or os.geteuid() != 0:
        raise RuntimeError("Disposable hosted root required")
    if Path("/.dockerenv").exists():
        raise RuntimeError("Refusing Docker; real Bubblewrap requires hosted Ubuntu")
    if os.environ.get("MYAI_HOSTED_FOUR_UID_BWRAP") != "yes":
        raise RuntimeError("Missing explicit GitHub-hosted opt-in")
    if os.environ.get("MYAI_RUNNER_ENVIRONMENT") != "github-hosted":
        raise RuntimeError("Not verified as a disposable GitHub-hosted runner")
    if not Path("/usr/bin/bwrap").is_file():
        raise RuntimeError("Real Bubblewrap missing; no fallback")


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
    """Verifier UID runs actual fixed Bubblewrap before any signing."""
    outcome = observe(trusted_fixture_root=private)
    if (
        outcome.fixture_sha256 != SOURCE_SHA
        or outcome.plan_sha256 != PLAN_SHA
        or outcome.sandbox != "bubblewrap"
        or outcome.network_isolated is not True
        or outcome.host_devices_exposed is not False
        or outcome.authorizes_mutation is not False
    ):
        raise RuntimeError("Incomplete real Bubblewrap observation")
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
            # This signature follows a genuine verifier-UID Bubblewrap run,
            # but this is a fixed synthetic fixture, never a production test.
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
    root = Path(tempfile.mkdtemp(prefix="myai-fouruid-real-bwrap-", dir="/tmp"))
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
        "fixed_synthetic_ast_executed_in_real_bubblewrap": True,
        "independent_verifier_uid_observed_real_bubblewrap": True,
        "all_cross_uid_key_reads_denied": True,
        "unauthorized_peers_rejected": 2,
        "forged_pass_flag_rejected": 1,
        "sqlite_replay_after_reopen_denied": True,
        "real_bubblewrap_namespace_and_readonly_proven_on_host": True,
        "production_verifier_service_implemented": False,
        "trusted_public_key_provisioning_proven": False,
        "real_ventuno_runner_or_acl_verified": False,
        "production_deployment_authorized": False,
        "physical_ventuno_tests_performed": False,
        "production_touched": False,
    }, sort_keys=True))


if __name__ == "__main__":
    main()
