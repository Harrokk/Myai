"""Disposable local SQLite candidate state tests. All signer keys are ephemeral."""
import concurrent.futures
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_verifier_key_rotation import (
    TrustedVerifierKey, ISSUER, AUDIENCE, PURPOSE,
    canonical_rotation, key_fingerprint,
)
from core.selfdev_verifier_key_state_preview import (
    CandidateTransition, CandidateSnapshot, initialize_candidate_schema,
    inspect_candidate_snapshot, seed_candidate_for_test,
    simulate_candidate_transition,
)

NOW = 1_800_000_000
NONCE = "d" * 32


def pair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def open_candidate(path):
    db = sqlite3.connect(path, timeout=5, isolation_level="DEFERRED")
    db.execute("PRAGMA synchronous=FULL")
    initialize_candidate_schema(db)
    return db


def prepared(tmp_path):
    old_private, old_public = pair()
    new_private, new_public = pair()
    checkpoint = TrustedVerifierKey(old_public, 4)
    path = tmp_path / "candidate-test.db"
    db = open_candidate(path)
    seed_candidate_for_test(db, externally_pinned_initial_key=checkpoint)
    payload = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "old_epoch": 4, "new_epoch": 5,
        "old_key_sha256": key_fingerprint(old_public),
        "new_key_hex": new_public.hex(),
        "new_key_sha256": key_fingerprint(new_public),
        "operator_nonce": NONCE,
        "not_before_unix": NOW - 5,
        "expires_unix": NOW + 60,
    }
    signed = canonical_rotation(payload)
    wire = json.dumps({
        "statement": payload,
        "previous_signature": old_private.sign(signed).hex(),
        "proposed_signature": new_private.sign(signed).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return path, db, checkpoint, (new_private, new_public), wire, hashlib.sha256(signed).hexdigest()


def rotate(db, checkpoint, wire, digest, **options):
    arguments = dict(
        independently_pinned_checkpoint=checkpoint,
        signed_envelope=wire,
        expected_operator_nonce=NONCE,
        independently_approved_payload_sha256=digest,
        now_unix=NOW,
    )
    arguments.update(options)
    return simulate_candidate_transition(db, **arguments)


def after(old_checkpoint, new_public):
    return TrustedVerifierKey(
        new_public, 5,
        frozenset({key_fingerprint(old_checkpoint.public_key)}),
    )


def test_candidate_transition_retires_old_key_without_real_activation(tmp_path):
    _, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    try:
        before = inspect_candidate_snapshot(db, independently_pinned_checkpoint=checkpoint)
        assert isinstance(before, CandidateSnapshot)
        assert before.epoch == 4
        assert before.retired_fingerprints == frozenset()
        result = rotate(db, checkpoint, wire, digest)
        assert isinstance(result, CandidateTransition)
        assert result.old_epoch == 4
        assert result.new_epoch == 5
        assert result.new_fingerprint == key_fingerprint(new_public)
        assert result.old_key_retired_in_candidate_database is True
        assert result.candidate_sqlite_transaction_committed is True
        assert result.independent_operator_authentication_verified is False
        assert result.independent_monotonic_checkpoint_updated is False
        assert result.actual_key_rotation_performed is False
        assert result.authorizes_mutation is False
        assert result.production_deployment_authorized is False
        current = inspect_candidate_snapshot(
            db, independently_pinned_checkpoint=after(checkpoint, new_public)
        )
        assert current.epoch == 5
        assert current.retired_fingerprints == frozenset({
            key_fingerprint(checkpoint.public_key)
        })
        assert current.storage_rollback_resistance_verified is False
        with pytest.raises(FrozenInstanceError):
            result.actual_key_rotation_performed = True
    finally:
        db.close()


def test_restart_keeps_candidate_epoch_revocation_and_nonce_history(tmp_path):
    path, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    rotate(db, checkpoint, wire, digest)
    db.close()
    db = open_candidate(path)
    try:
        current = inspect_candidate_snapshot(
            db, independently_pinned_checkpoint=after(checkpoint, new_public)
        )
        assert current.epoch == 5
        assert len(current.retired_fingerprints) == 1
        assert db.execute(
            "SELECT COUNT(*) FROM candidate_verifier_transitions"
        ).fetchone()[0] == 1
        with pytest.raises(ValueError):
            rotate(db, checkpoint, wire, digest)
        assert db.in_transaction is False
    finally:
        db.close()


def test_old_database_snapshot_detected_only_with_independent_new_checkpoint(tmp_path):
    path, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    db.close()
    backup = tmp_path / "old-copy.db"
    shutil.copyfile(path, backup)
    db = open_candidate(path)
    rotate(db, checkpoint, wire, digest)
    db.close()
    old_snapshot = open_candidate(backup)
    try:
        # A properly advanced, separate trust anchor detects the rollback.
        with pytest.raises(ValueError, match="checkpoint"):
            inspect_candidate_snapshot(
                old_snapshot,
                independently_pinned_checkpoint=after(checkpoint, new_public),
            )
        with pytest.raises(ValueError, match="checkpoint"):
            rotate(
                old_snapshot, after(checkpoint, new_public), wire, digest
            )
        # A *stale* checkpoint would NOT detect this rollback. Do not claim
        # cryptographic rollback resistance from SQLite by itself.
        assert inspect_candidate_snapshot(
            old_snapshot, independently_pinned_checkpoint=checkpoint
        ).epoch == 4
    finally:
        old_snapshot.close()


def test_reusing_old_private_signing_key_cannot_pass_latest_candidate_state(tmp_path):
    _, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    try:
        rotate(db, checkpoint, wire, digest)
        with pytest.raises(ValueError):
            rotate(db, after(checkpoint, new_public), wire, digest)
        assert db.execute("SELECT count(*) FROM candidate_verifier_transitions").fetchone()[0] == 1
    finally:
        db.close()


def test_mismatched_independent_revocations_rejected_even_when_key_matches(tmp_path):
    _, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    try:
        rotate(db, checkpoint, wire, digest)
        with pytest.raises(ValueError, match="revocations"):
            inspect_candidate_snapshot(
                db, independently_pinned_checkpoint=TrustedVerifierKey(new_public, 5)
            )
        with pytest.raises(ValueError, match="revocations"):
            rotate(db, TrustedVerifierKey(new_public, 5), wire, digest)
    finally:
        db.close()


def test_candidate_database_key_tampering_cannot_satisfy_separate_checkpoint(tmp_path):
    _, db, checkpoint, _, _, _ = prepared(tmp_path)
    other_public = pair()[1]
    db.execute(
        "UPDATE candidate_verifier_state SET public_key=?, fingerprint=? WHERE singleton=1",
        (other_public, key_fingerprint(other_public)),
    )
    db.commit()
    try:
        with pytest.raises(ValueError, match="checkpoint"):
            inspect_candidate_snapshot(
                db, independently_pinned_checkpoint=checkpoint
            )
    finally:
        db.close()


@pytest.mark.parametrize("mutation", [
    "unknown_digest", "changed_nonce", "changed_signature",
    "old_epoch_changed", "expired", "future", "new_key_revoked",
])
def test_failed_validation_never_changes_candidate_db(tmp_path, mutation):
    _, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    options = {}
    if mutation == "unknown_digest":
        digest = "0" * 64
    if mutation == "changed_nonce":
        options["expected_operator_nonce"] = "e" * 32
    if mutation in ("changed_signature", "old_epoch_changed"):
        body = json.loads(wire)
        if mutation == "changed_signature":
            body["previous_signature"] = "0" * 128
        else:
            body["statement"]["old_epoch"] = 3
        wire = json.dumps(body).encode()
    if mutation == "expired":
        options["now_unix"] = NOW + 65
    if mutation == "future":
        options["now_unix"] = NOW - 10
    if mutation == "new_key_revoked":
        # Independent checkpoint's revocation and DB must BOTH agree.
        db.execute(
            "INSERT INTO candidate_verifier_revoked(fingerprint,retired_at_epoch) VALUES (?,?)",
            (key_fingerprint(new_public), 3),
        )
        db.commit()
        checkpoint = TrustedVerifierKey(
            checkpoint.public_key, 4,
            frozenset({key_fingerprint(new_public)}),
        )
    try:
        with pytest.raises(ValueError):
            rotate(db, checkpoint, wire, digest, **options)
        assert db.in_transaction is False
        assert db.execute(
            "SELECT epoch FROM candidate_verifier_state"
        ).fetchone()[0] == 4
        assert db.execute(
            "SELECT COUNT(*) FROM candidate_verifier_transitions"
        ).fetchone()[0] == 0
    finally:
        db.close()


def test_bootstrap_twice_and_untrusted_revocation_bootstrap_rejected(tmp_path):
    _, db, checkpoint, _, _, _ = prepared(tmp_path)
    try:
        with pytest.raises(ValueError, match="already"):
            seed_candidate_for_test(
                db, externally_pinned_initial_key=checkpoint
            )
        with pytest.raises(ValueError, match="recovery"):
            seed_candidate_for_test(
                db, externally_pinned_initial_key=TrustedVerifierKey(
                    checkpoint.public_key, 4, frozenset({"a" * 64}),
                )
            )
        assert db.in_transaction is False
    finally:
        db.close()


def test_no_trust_anchor_or_non_sqlite_input_is_accepted(tmp_path):
    path, db, checkpoint, _, wire, digest = prepared(tmp_path)
    try:
        for bad in (None, {}, True, "trust-me"):
            with pytest.raises(ValueError):
                inspect_candidate_snapshot(
                    db, independently_pinned_checkpoint=bad
                )
        with pytest.raises(ValueError):
            simulate_candidate_transition(
                "not db", independently_pinned_checkpoint=checkpoint,
                signed_envelope=wire, expected_operator_nonce=NONCE,
                independently_approved_payload_sha256=digest, now_unix=NOW,
            )
    finally:
        db.close()


def test_concurrent_candidate_rotation_allows_one_transaction_only(tmp_path):
    path, db, checkpoint, (_, new_public), wire, digest = prepared(tmp_path)
    db.close()
    barrier = threading.Barrier(2)
    def attempt():
        conn = open_candidate(path)
        try:
            barrier.wait(timeout=3)
            try:
                rotate(conn, checkpoint, wire, digest)
                return "committed"
            except ValueError:
                return "rejected"
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(attempt) for _ in range(2)]
        outcomes = [f.result(timeout=8) for f in futures]
    assert sorted(outcomes) == ["committed", "rejected"]
    db = open_candidate(path)
    try:
        assert inspect_candidate_snapshot(
            db, independently_pinned_checkpoint=after(checkpoint, new_public)
        ).epoch == 5
        assert db.execute(
            "SELECT count(*) FROM candidate_verifier_transitions"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_candidate_scenario_does_not_touch_real_key_management_or_promotion():
    import core.selfdev_verifier_key_state_preview as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    for dangerous in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager", "os.chmod(",
        "os.chown(", "open(", "production_deployment_authorized: bool = True",
    ):
        assert dangerous not in source
    assert "production_deployment_authorized: bool = False" in source
    assert "actual_key_rotation_performed: bool = False" in source
