"""Throwaway-key-only regression tests for candidate operator nonce consumption."""
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

from core.selfdev_operator_signed_review import (
    ISSUER as O_ISSUER, PURPOSE as O_PURPOSE, AUDIENCE as O_AUDIENCE,
    canonical_operator_review,
)
from core.selfdev_verifier_key_rotation import (
    TrustedVerifierKey, ISSUER as V_ISSUER, PURPOSE as V_PURPOSE,
    AUDIENCE as V_AUDIENCE, key_fingerprint, canonical_rotation,
)
from core.selfdev_operator_nonce_ledger import (
    initialize_operator_review_ledger, issue_operator_review_challenge,
    consume_operator_review_once, InspectedOperatorReview, PendingOperatorReview,
)

NOW = 1_800_000_000
DEVICE = "ventuno-offline-only"
NONCE = "d" * 32


def keypair():
    private = Ed25519PrivateKey.generate()  # Only throwaway test keys
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def connection(path):
    conn = sqlite3.connect(path, timeout=5)
    conn.execute("PRAGMA synchronous=FULL")
    initialize_operator_review_ledger(conn)
    return conn


def signing_inputs():
    prev, prev_pub = keypair()
    nxt, next_pub = keypair()
    op, op_pub = keypair()
    anchor = TrustedVerifierKey(prev_pub, 4)
    statement = {
        "version": 1, "issuer": V_ISSUER, "purpose": V_PURPOSE,
        "audience": V_AUDIENCE,
        "old_epoch": 4, "new_epoch": 5,
        "old_key_sha256": key_fingerprint(prev_pub),
        "new_key_hex": next_pub.hex(),
        "new_key_sha256": key_fingerprint(next_pub),
        "operator_nonce": NONCE,
        "not_before_unix": NOW - 15, "expires_unix": NOW + 70,
    }
    signed = canonical_rotation(statement)
    rotated = json.dumps({
        "statement": statement, "previous_signature": prev.sign(signed).hex(),
        "proposed_signature": nxt.sign(signed).hex(),
    }, separators=(",", ":"), sort_keys=True).encode()
    digest = hashlib.sha256(signed).hexdigest()
    review = {
        "version": 1, "issuer": O_ISSUER, "purpose": O_PURPOSE,
        "audience": O_AUDIENCE, "device_id": DEVICE,
        "rotation_sha256": digest, "old_key_sha256": key_fingerprint(prev_pub),
        "new_key_sha256": key_fingerprint(next_pub),
        "old_epoch": 4, "new_epoch": 5,
        "operator_challenge": NONCE, "not_before_unix": NOW - 5,
        "expires_unix": NOW + 50,
    }
    review_bytes = canonical_operator_review(review)
    operator_wire = json.dumps({
        "statement": review, "signature": op.sign(review_bytes).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return {
        "anchor": anchor, "operator_key": op_pub,
        "new_fingerprint": key_fingerprint(next_pub),
        "rotation_digest": digest, "operator_wire": operator_wire,
        "rotation_wire": rotated,
    }


def issue(db, context, **kwargs):
    values = dict(
        trusted_verifier_anchor=context["anchor"],
        trusted_operator_public_key=context["operator_key"],
        device_id=DEVICE, rotation_sha256=context["rotation_digest"],
        proposed_key_sha256=context["new_fingerprint"],
        now_unix=NOW, nonce_factory=lambda n: NONCE,
    )
    values.update(kwargs)
    return issue_operator_review_challenge(db, **values)


def consume(db, context, **kwargs):
    values = dict(
        operator_envelope=context["operator_wire"],
        rotation_envelope=context["rotation_wire"],
        trusted_verifier_anchor=context["anchor"],
        trusted_operator_public_key=context["operator_key"],
        expected_device_id=DEVICE, expected_challenge=NONCE, now_unix=NOW + 1,
    )
    values.update(kwargs)
    return consume_operator_review_once(db, **values)


def test_single_use_after_triple_signature_and_no_production_authorization(tmp_path):
    db = connection(tmp_path / "approval.db")
    ctx = signing_inputs()
    try:
        challenge = issue(db, ctx)
        assert isinstance(challenge, PendingOperatorReview)
        assert challenge.challenge == NONCE
        assert challenge.authorizes_mutation is False
        reviewed = consume(db, ctx)
        assert isinstance(reviewed, InspectedOperatorReview)
        assert reviewed.old_epoch == 4 and reviewed.proposed_epoch == 5
        assert reviewed.rotation_sha256 == ctx["rotation_digest"]
        assert reviewed.all_three_signature_checks_passed is True
        assert reviewed.one_time_sqlite_candidate_consumption_observed is True
        assert reviewed.independent_human_approval_verified is False
        assert reviewed.external_rollback_checkpoint_advanced is False
        assert reviewed.verifier_key_activated is False
        assert reviewed.authorizes_mutation is False
        assert reviewed.production_deployment_authorized is False
        with pytest.raises(FrozenInstanceError):
            reviewed.verifier_key_activated = True
        with pytest.raises(ValueError, match="consumed"):
            consume(db, ctx)
    finally:
        db.close()


def test_reopen_database_cannot_reuse_consumed_operator_challenge(tmp_path):
    path = tmp_path / "approval.db"
    db = connection(path)
    ctx = signing_inputs()
    issue(db, ctx)
    consume(db, ctx)
    db.close()
    db = connection(path)
    try:
        with pytest.raises(ValueError, match="consumed"):
            consume(db, ctx)
        assert db.execute(
            "SELECT COUNT(*) FROM candidate_operator_challenges"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_backup_rollback_requires_external_consumed_checkpoint(tmp_path):
    path = tmp_path / "approval.db"
    backup = tmp_path / "stale.db"
    db = connection(path)
    ctx = signing_inputs()
    issue(db, ctx)
    db.close()
    shutil.copyfile(path, backup)
    db = connection(path)
    consume(db, ctx)
    db.close()
    old_db = connection(backup)
    try:
        # Separate protected evidence would deny this restored DB record.
        with pytest.raises(ValueError, match="External checkpoint"):
            consume(old_db, ctx, independently_consumed_nonces=frozenset({NONCE}))
        assert old_db.execute(
            "SELECT consumed_unix FROM candidate_operator_challenges"
        ).fetchone()[0] is None
        # Deliberate negative demonstration: stale DB plus stale/empty external
        # checkpoint permits replay. This code makes NO anti-rollback claims.
        replay_from_restored_file = consume(old_db, ctx)
        assert replay_from_restored_file.external_rollback_checkpoint_advanced is False
    finally:
        old_db.close()


def test_two_independent_connections_only_one_can_consume_same_nonce(tmp_path):
    path = tmp_path / "same.db"
    db = connection(path)
    ctx = signing_inputs()
    issue(db, ctx)
    db.close()
    gate = threading.Barrier(2)
    def worker():
        conn = connection(path)
        try:
            gate.wait(timeout=5)
            try:
                consume(conn, ctx)
                return "used"
            except ValueError:
                return "rejected"
        finally:
            conn.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(worker) for _ in range(2)]
        assert sorted(f.result(timeout=12) for f in futures) == ["rejected", "used"]
    db = connection(path)
    try:
        assert db.execute(
            "SELECT COUNT(*) FROM candidate_operator_challenges WHERE consumed_unix IS NOT NULL"
        ).fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize("problem", [
    "bad_operator_signature", "bad_old_verifier_signature",
    "bad_new_verifier_signature", "other_device", "bad_digest",
    "other_nonce", "wrong_operator_public_key", "different_verifier_epoch",
    "wrong_signed_new_fingerprint", "expired_review", "expired_challenge",
    "before_issuance",
])
def test_invalid_context_and_signatures_fail_without_consuming(tmp_path, problem):
    db = connection(tmp_path / "fail.db")
    ctx = signing_inputs()
    issue(db, ctx)
    kwargs = {}
    if problem in ("bad_operator_signature", "wrong_signed_new_fingerprint"):
        obj = json.loads(ctx["operator_wire"])
        if problem == "bad_operator_signature":
            obj["signature"] = "0" * 128
        else:
            obj["statement"]["new_key_sha256"] = "f" * 64
        kwargs["operator_envelope"] = json.dumps(obj).encode()
    if problem in ("bad_old_verifier_signature", "bad_new_verifier_signature"):
        obj = json.loads(ctx["rotation_wire"])
        field = "previous_signature" if problem.startswith("bad_old") else "proposed_signature"
        obj[field] = "0" * 128
        kwargs["rotation_envelope"] = json.dumps(obj).encode()
    if problem == "other_device":
        kwargs["expected_device_id"] = "other_ventuno"
    if problem == "bad_digest":
        db.execute(
            "UPDATE candidate_operator_challenges SET rotation_sha256=?",
            ("f" * 64,),
        )
        db.commit()
    if problem == "other_nonce":
        kwargs["expected_challenge"] = "e" * 32
    if problem == "wrong_operator_public_key":
        kwargs["trusted_operator_public_key"] = keypair()[1]
    if problem == "different_verifier_epoch":
        ctx["anchor"] = TrustedVerifierKey(ctx["anchor"].public_key, 5)
    if problem in ("expired_review", "expired_challenge", "before_issuance"):
        kwargs["now_unix"] = {
            "expired_review": NOW + 51,
            "expired_challenge": NOW + 121,
            "before_issuance": NOW - 1,
        }[problem]
    try:
        with pytest.raises(ValueError):
            consume(db, ctx, **kwargs)
        assert db.in_transaction is False
        assert db.execute(
            "SELECT consumed_unix FROM candidate_operator_challenges"
        ).fetchone()[0] is None
    finally:
        db.close()


def test_duplicate_operator_nonce_never_reissued(tmp_path):
    db = connection(tmp_path / "duplicate.db")
    ctx = signing_inputs()
    try:
        issue(db, ctx)
        with pytest.raises(sqlite3.IntegrityError):
            issue(db, ctx)
        assert db.in_transaction is False
        assert db.execute("SELECT COUNT(*) FROM candidate_operator_challenges").fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize("bad_lifetime", [0, -1, 301, True, 1.5, "60"])
def test_invalid_expiry_refused_before_issue(tmp_path, bad_lifetime):
    db = connection(tmp_path / "expiry.db")
    try:
        with pytest.raises(ValueError):
            issue(db, signing_inputs(), lifetime_seconds=bad_lifetime)
        assert db.execute("SELECT COUNT(*) FROM candidate_operator_challenges").fetchone()[0] == 0
    finally:
        db.close()


@pytest.mark.parametrize("bad_nonce", ["D" * 32, "x", True, 123, None])
def test_nonce_factory_fails_closed_on_noncanonical_nonce(tmp_path, bad_nonce):
    db = connection(tmp_path / "nonce.db")
    try:
        with pytest.raises(ValueError):
            issue(db, signing_inputs(), nonce_factory=lambda _: bad_nonce)
    finally:
        db.close()


@pytest.mark.parametrize("bad", [
    None, [], set(), frozenset({"a" * 31}), frozenset({"F" * 32}),
    frozenset({123}), frozenset({"f" * 32} * 257),
])
def test_untrusted_external_checkpoint_never_accepted(tmp_path, bad):
    db = connection(tmp_path / "checkpoint.db")
    ctx = signing_inputs()
    try:
        issue(db, ctx)
        with pytest.raises(ValueError):
            consume(db, ctx, independently_consumed_nonces=bad)
    finally:
        db.close()


def test_missing_challenge_never_accepts_valid_signed_review(tmp_path):
    db = connection(tmp_path / "missing.db")
    try:
        with pytest.raises(ValueError, match="missing"):
            consume(db, signing_inputs())
    finally:
        db.close()


def test_no_signer_or_production_activation_in_offline_module():
    import core.selfdev_operator_nonce_ledger as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.", "systemctl",
        "SelfDevPromotionManager", "os.chown(", "os.chmod(", "save_verification(",
    ):
        assert forbidden not in source
    assert "external_rollback_checkpoint_advanced: bool = False" in source
    assert "production_deployment_authorized: bool = False" in source
