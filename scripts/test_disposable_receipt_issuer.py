"""DISPOSABLE GitHub-hosted 4-UID REAL Linux receipt signer integration.

Signer UID 23006 creates its Ed25519 key AFTER dropping privileges, then
reads only signer-owned test SQLite journal and signed witness fixture.
UPDATER UID 23001 can request fixed inspection with nonce only. Runtime and
CI UIDs are denied using SO_PEERCRED. The signer never takes passed, command,
paths, signature, result or keys from an IPC request. This is synthetic and
NOT a production write-observation service or durable replay protection.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import tempfile
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_candidate_crash_intent_journal import (
    STAGES, initialize_candidate_intent_journal, create_candidate_intent,
    record_candidate_milestone,
)
from core.selfdev_receipt_issuer_preview import inspect_candidate_for_receipt
from core.selfdev_receipt_signer_nonce_ledger import (
    initialize_signer_candidate_nonce_ledger, claim_receipt_once,
)
from core.selfdev_signed_witness_checkpoint import (
    ISSUER as W_ISSUER, PURPOSE as W_PURPOSE, AUDIENCE as W_AUDIENCE,
    canonical_witness_checkpoint,
)
from core.selfdev_signed_witness_milestone import (
    canonical_milestone_receipt, inspect_signed_witness_milestone,
)
from core.selfdev_unix_peercred import (
    require_peer_uid, receive_frame, send_frame, parse_inspection_message,
)

UPDATER, RUNTIME, CI, SIGNER = 23001, 23002, 23003, 23006
DEVICE = "disposable_receipt_signer"
INTENT = "fixed_receipt_test"
NONCE = "a" * 32
ROTATION = "b" * 64
ATTEMPTS = ((RUNTIME, "untrusted"), (CI, "untrusted"),
            (UPDATER, "forged"), (UPDATER, "valid"), (UPDATER, "replay"))


def gate():
    if (os.name != "posix" or os.geteuid() != 0
            or Path("/.dockerenv").exists()
            or os.environ.get("MYAI_HOSTED_RECEIPT_UID_TEST") != "yes"
            or os.environ.get("MYAI_RUNNER_ENVIRONMENT") != "github-hosted"):
        raise RuntimeError("Root allowed only inside explicit disposable hosted UID test")


def drop(uid):
    os.setgroups([])
    os.setgid(uid)
    os.setuid(uid)
    assert os.geteuid() == uid


def fork(fn, *args):
    reader, writer = os.pipe()
    pid = os.fork()
    if pid == 0:
        os.close(reader)
        try:
            record = fn(*args)
            encoded = json.dumps(record, sort_keys=True).encode("ascii")
            if len(encoded) > 4000:
                raise ValueError("Unbounded private child report")
            os.write(writer, encoded)
            os._exit(0)
        except BaseException as error:
            os.write(writer, type(error).__name__.encode("ascii", "replace"))
            os._exit(1)
    os.close(writer)
    return pid, reader


def join(pid, reader):
    data = os.read(reader, 4096)
    os.close(reader)
    _, status = os.waitpid(pid, 0)
    if not os.WIFEXITED(status) or os.WEXITSTATUS(status) != 0:
        raise AssertionError("Disposable child failure: "
                             + data.decode("ascii", "replace")[:72])
    return json.loads(data)


def witness_record(private, verifier_key, *, seq, parent, consumed):
    record = {
        "version": 1, "issuer": W_ISSUER, "purpose": W_PURPOSE,
        "audience": W_AUDIENCE, "device_id": DEVICE,
        "sequence": seq, "verifier_epoch": 4,
        "verifier_public_key_hex": verifier_key.hex(),
        "verifier_fingerprint": hashlib.sha256(verifier_key).hexdigest(),
        "retired_verifier_fingerprints": [],
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": parent, "recorded_unix": 1800000000+seq,
    }
    blob = canonical_witness_checkpoint(record)
    encoded = json.dumps({
        "statement": record,
        "signature": private.sign(blob).hex(),
    }, separators=(",", ":"), sort_keys=True).encode()
    return encoded, hashlib.sha256(blob).hexdigest()


def create_fixed_fixture(private_dir):
    # Only the synthetic test orchestrator may create the private fixture.
    witness_secret = Ed25519PrivateKey.generate()
    witness_pub = witness_secret.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw,
    )
    verifier = Ed25519PrivateKey.generate().public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw,
    )
    initial, genesis = witness_record(
        witness_secret, verifier, seq=1, parent="0"*64, consumed=(),
    )
    second, head = witness_record(
        witness_secret, verifier, seq=2, parent=genesis, consumed=(NONCE,),
    )
    journal_path = private_dir / "journal.sqlite"
    conn = sqlite3.connect(journal_path)
    initialize_candidate_intent_journal(conn)
    create_candidate_intent(
        conn, intent_id=INTENT, device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION,
        expected_operator_witness_head=head,
        expected_final_witness_head="c"*64,
        created_unix=1800000000,
    )
    record_candidate_milestone(conn, intent_id=INTENT, next_stage=STAGES[1])
    record_candidate_milestone(
        conn, intent_id=INTENT, next_stage=STAGES[2],
        observed_witness_head=head,
    )
    conn.close()
    os.chown(journal_path, SIGNER, SIGNER)
    os.chmod(journal_path, 0o600)
    witness_path = private_dir / "signed-witness.json"
    witness_path.write_bytes(json.dumps(
        [initial.hex(), second.hex()], separators=(",", ":"),
    ).encode("ascii"))
    os.chown(witness_path, SIGNER, SIGNER)
    os.chmod(witness_path, 0o600)
    return journal_path, witness_path, witness_pub, genesis, head


def issuer(listener, private_dir, witness_pub, genesis, head, public_pipe):
    drop(SIGNER)
    signing_key = Ed25519PrivateKey.generate()
    public = signing_key.public_key().public_bytes(
        Encoding.Raw, PublicFormat.Raw,
    )
    os.write(public_pipe, public)
    os.close(public_pipe)
    allowed = denied = malformed = replay = 0
    os.umask(0o077)  # signer-owned new SQLite nonce state only
    for _ in ATTEMPTS:
        connection, _ = listener.accept()
        with connection:
            connection.settimeout(4.0)
            try:
                require_peer_uid(connection, expected_uid=UPDATER)
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
            if challenge != NONCE:
                send_frame(connection, b'{"status":"challenge_denied"}')
                replay += 1
                continue
            # Neither the command nor any proposed result comes from IPC.
            if (private_dir.stat().st_uid != SIGNER
                    or private_dir.stat().st_mode & 0o777 != 0o700):
                raise PermissionError("Signer-private state ownership changed")
            for filename in ("journal.sqlite", "signed-witness.json"):
                path = private_dir / filename
                if (path.is_symlink() or path.stat().st_uid != SIGNER
                        or path.stat().st_mode & 0o777 != 0o600):
                    raise PermissionError("Private fixture ownership mismatch")
            witness_data = json.loads(
                (private_dir / "signed-witness.json").read_text("ascii")
            )
            witness_chain = [bytes.fromhex(x) for x in witness_data]
            db = sqlite3.connect(private_dir / "journal.sqlite")
            try:
                inspected = inspect_candidate_for_receipt(
                    private_journal_db=db, witness_envelopes=witness_chain,
                    pinned_witness_public_key=witness_pub,
                    pinned_genesis_sha256=genesis, pinned_latest_sha256=head,
                    expected_device_id=DEVICE, expected_intent_id=INTENT,
                    trusted_now_unix=int(time.time()),
                )
            finally:
                db.close()
            statement = inspected.statement
            assert statement["operator_nonce"] == challenge
            nonce_db_path = private_dir / "signer-consumed.sqlite"
            nonce_db = sqlite3.connect(nonce_db_path, timeout=3)
            try:
                initialize_signer_candidate_nonce_ledger(nonce_db)
                try:
                    claim_receipt_once(
                        nonce_db, challenge=challenge,
                        device_id=statement["device_id"],
                        intent_id=statement["intent_id"],
                        signed_witness_head_sha256=statement["witness_head_sha256"],
                        journal_event_sha256=statement["journal_event_sha256"],
                        now_unix=statement["verified_unix"],
                        expires_unix=statement["expires_unix"],
                    )
                except ValueError:
                    send_frame(connection, b'{"status":"challenge_denied"}')
                    replay += 1
                    continue
            finally:
                nonce_db.close()
            if (nonce_db_path.stat().st_uid != SIGNER
                    or nonce_db_path.stat().st_mode & 0o777 != 0o600):
                raise PermissionError("Signer-owned nonce DB lost private DAC")
            # Consumed challenge commits BEFORE a signature can be issued.
            # A crash here permanently denies retry unless DB is rolled back.
            signature = signing_key.sign(canonical_milestone_receipt(statement))
            envelope = json.dumps({
                "statement": statement, "signature": signature.hex(),
            }, separators=(",", ":"), sort_keys=True).encode("ascii")
            send_frame(connection, envelope)
            allowed += 1
    listener.close()
    return {"signer_uid": os.geteuid(), "accepted": allowed,
            "denied_peers": denied, "denied_extra_request_fields": malformed,
            "denied_replay_within_process": replay,
            "private_key_serialized": False}


def probe(listener, address, private_dir, uid, intent):
    listener.close()
    drop(uid)
    for name in ("journal.sqlite", "signed-witness.json"):
        try:
            (private_dir / name).read_bytes()
        except PermissionError:
            pass
        else:
            raise AssertionError("Other role can read signer-owned private fixture")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(4.0)
        client.connect(address)
        if intent != "untrusted":
            request = {
                "version": 1, "action": "inspect_fixed_fixture",
                "challenge": NONCE,
            }
            if intent == "forged":
                request["passed"] = True
            send_frame(client, json.dumps(request).encode("ascii"))
        reply = receive_frame(client)
    if intent == "untrusted":
        assert json.loads(reply) == {"status": "peer_denied"}
    elif intent == "forged":
        assert json.loads(reply) == {"status": "request_denied"}
    elif intent == "replay":
        assert json.loads(reply) == {"status": "challenge_denied"}
    else:
        obj = json.loads(reply)
        assert set(obj) == {"statement", "signature"}
        assert obj["statement"]["operator_nonce"] == NONCE
        return {"intent": intent, "receipt_hex": reply.hex()}
    return {"intent": intent}


def main():
    gate()
    root = Path(tempfile.mkdtemp(prefix="myai-receipt-issuer-", dir="/tmp"))
    root.chmod(0o755)
    private_dir = root / "private-signer"
    private_dir.mkdir()
    try:
        journal, witness_path, witness_pub, genesis, head = create_fixed_fixture(
            private_dir,
        )
        os.chown(private_dir, SIGNER, SIGNER)
        private_dir.chmod(0o700)
        address = str(root / "inspection.sock")
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
            server.settimeout(12.0)
            server.bind(address)
            os.chmod(address, 0o666)  # deliberate: exercise kernel peer auth
            server.listen(5)
            pub_r, pub_w = os.pipe()
            pid, report_pipe = fork(
                issuer, server, private_dir, witness_pub, genesis, head, pub_w,
            )
            os.close(pub_w)
            receipt_pub = os.read(pub_r, 32)
            os.close(pub_r)
            assert len(receipt_pub) == 32
            responses = []
            for uid, intent in ATTEMPTS:
                child_pid, child_report = fork(
                    probe, server, address, private_dir, uid, intent,
                )
                responses.append(join(child_pid, child_report))
            outcome = join(pid, report_pipe)
        nonce_file = private_dir / "signer-consumed.sqlite"
        assert nonce_file.stat().st_uid == SIGNER
        assert nonce_file.stat().st_mode & 0o777 == 0o600
        protected = sqlite3.connect(nonce_file)
        try:
            assert protected.execute(
                "SELECT count(*) FROM candidate_signer_consumed_receipts"
            ).fetchone()[0] == 1
        finally:
            protected.close()
        assert outcome == {
            "signer_uid": SIGNER, "accepted": 1,
            "denied_peers": 2, "denied_extra_request_fields": 1,
            "denied_replay_within_process": 1,
            "private_key_serialized": False,
        }
        result = next(x for x in responses if x["intent"] == "valid")
        # Root in this disposable test verifies source consistency. A live
        # updater would need its OWN trusted journal snapshot/provisioning.
        conn = sqlite3.connect(journal)
        try:
            verified = inspect_signed_witness_milestone(
                journal_db=conn, receipt_envelope=bytes.fromhex(
                    result["receipt_hex"]
                ),
                witness_envelopes=[bytes.fromhex(x) for x in
                    json.loads(witness_path.read_text("ascii"))],
                trusted_receipt_public_key=receipt_pub,
                trusted_witness_public_key=witness_pub,
                independently_pinned_genesis_sha256=genesis,
                independently_pinned_latest_sha256=head,
                expected_device_id=DEVICE, expected_intent_id=INTENT,
                now_unix=int(time.time()),
            )
        finally:
            conn.close()
        assert verified.receipt_signature_verified
        assert verified.production_deployment_authorized is False
        assert verified.real_external_write_observed is False
        print("MYAI_DISPOSABLE_RECEIPT_ISSUER_JSON=" + json.dumps({
            "status": "PASS", "real_linux_uids": 4,
            "signer_uid": SIGNER, "signer_key_generated_after_uid_drop": True,
            "protected_synthetic_witness_and_journal_inspected": True,
            "runtime_ci_peers_rejected": 2,
            "forged_passed_flag_rejected": True,
            "replay_within_live_signer_denied": True,
            "signer_owned_sqlite_replay_state_persisted": True,
            "synthetic_signer_key_and_nonce_db_are_separate": True,
            "real_disk_write_proven": False,
            "durable_nonce_replay_protection_proven": False,
            "fresh_external_head_proven": False,
            "independent_production_signer_installed": False,
            "production_deployment_authorized": False,
            "ventuno_touched": False,
        }, sort_keys=True))
    finally:
        shutil.rmtree(root)


if __name__ == "__main__":
    main()
