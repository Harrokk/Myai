"""OFF-DEVICE candidate SQLite consumption of operator-signed rotation reviews.

This is a NON-AUTHORIZING source-only test primitive. The connection is
provided by an already trusted caller; this module cannot open files, provision
operator keys, authenticate a human, alter active verifier keys or selfdev
promotion, or preserve a rollback-resistant external consumption checkpoint.
A rolled-back SQLite file can replay old challenges UNLESS independently
maintained consumed-nonce evidence survives the rollback.
"""
from __future__ import annotations

from dataclasses import dataclass
import secrets
import sqlite3

from core.selfdev_operator_signed_review import (
    DEVICE, HEX32, HEX64, MAX_DURATION, inspect_operator_review,
)
from core.selfdev_verifier_key_rotation import (
    _validate_anchor, key_fingerprint,
)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS candidate_operator_challenges (
  challenge TEXT PRIMARY KEY NOT NULL CHECK (length(challenge) = 32),
  device_id TEXT NOT NULL,
  old_epoch INTEGER NOT NULL,
  old_fingerprint TEXT NOT NULL,
  new_fingerprint TEXT NOT NULL,
  rotation_sha256 TEXT NOT NULL,
  operator_fingerprint TEXT NOT NULL,
  issued_unix INTEGER NOT NULL,
  expires_unix INTEGER NOT NULL,
  consumed_unix INTEGER,
  CHECK (expires_unix > issued_unix),
  CHECK (expires_unix - issued_unix <= 300),
  CHECK (consumed_unix IS NULL OR consumed_unix >= issued_unix)
)
"""


@dataclass(frozen=True)
class PendingOperatorReview:
    challenge: str
    expires_unix: int
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


@dataclass(frozen=True)
class InspectedOperatorReview:
    challenge: str
    device_id: str
    old_epoch: int
    proposed_epoch: int
    rotation_sha256: str
    all_three_signature_checks_passed: bool = True
    one_time_sqlite_candidate_consumption_observed: bool = True
    independent_human_approval_verified: bool = False
    external_rollback_checkpoint_advanced: bool = False
    verifier_key_activated: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _begin(db):
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ValueError("Caller-supplied SQLite connection with no active transaction required")
    db.execute("BEGIN IMMEDIATE")


def initialize_operator_review_ledger(db):
    """Initialize candidate-only schema; never opens or selects a database."""
    _begin(db)
    try:
        db.execute(_SCHEMA)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def _expected_context(*, trusted_verifier_anchor, trusted_operator_public_key,
                      device_id, rotation_sha256, proposed_key_sha256, now_unix):
    old_fingerprint = _validate_anchor(trusted_verifier_anchor)
    operator_fingerprint = key_fingerprint(trusted_operator_public_key)
    if (operator_fingerprint == old_fingerprint
            or operator_fingerprint == proposed_key_sha256):
        raise ValueError("Operator and verifier signing identities must be distinct")
    if type(device_id) is not str or DEVICE.fullmatch(device_id) is None:
        raise ValueError("Trusted target device identifier is invalid")
    if (type(rotation_sha256) is not str
            or HEX64.fullmatch(rotation_sha256) is None
            or type(proposed_key_sha256) is not str
            or HEX64.fullmatch(proposed_key_sha256) is None
            or proposed_key_sha256 == old_fingerprint
            or proposed_key_sha256 in trusted_verifier_anchor.revoked_fingerprints):
        raise ValueError("Invalid or revoked proposed verifier key / rotation digest")
    if type(now_unix) is not int or now_unix < 0:
        raise ValueError("Invalid trusted clock")
    return old_fingerprint, operator_fingerprint


def issue_operator_review_challenge(
    db, *, trusted_verifier_anchor, trusted_operator_public_key,
    device_id, rotation_sha256, proposed_key_sha256,
    now_unix, lifetime_seconds=120, nonce_factory=secrets.token_hex,
):
    """Issue a challenge linked to independently supplied trusted context.

    The runtime or review envelope MUST NOT be permitted to choose the nonce,
    public keys, verified target device or expected rotation digest.
    nonce_factory injection exists for deterministic TESTS ONLY.
    """
    old, operator = _expected_context(
        trusted_verifier_anchor=trusted_verifier_anchor,
        trusted_operator_public_key=trusted_operator_public_key,
        device_id=device_id, rotation_sha256=rotation_sha256,
        proposed_key_sha256=proposed_key_sha256, now_unix=now_unix,
    )
    if (type(lifetime_seconds) is not int
            or not 1 <= lifetime_seconds <= MAX_DURATION):
        raise ValueError("Invalid operator challenge lifetime")
    nonce = nonce_factory(16)
    if type(nonce) is not str or HEX32.fullmatch(nonce) is None:
        raise ValueError("Invalid updater-generated operator challenge")
    _begin(db)
    try:
        db.execute(
            """INSERT INTO candidate_operator_challenges
               (challenge, device_id, old_epoch, old_fingerprint,
                new_fingerprint, rotation_sha256, operator_fingerprint,
                issued_unix, expires_unix)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (nonce, device_id, trusted_verifier_anchor.epoch, old,
             proposed_key_sha256, rotation_sha256, operator, now_unix,
             now_unix + lifetime_seconds),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return PendingOperatorReview(nonce, now_unix + lifetime_seconds)


def consume_operator_review_once(
    db, *, operator_envelope, rotation_envelope,
    trusted_verifier_anchor, trusted_operator_public_key,
    expected_device_id, expected_challenge, now_unix,
    independently_consumed_nonces=frozenset(),
):
    """Atomically consume only after full independent triple-signature review.

    Independently consumed nonces are caller-supplied protection against
    SQLite snapshot rollback; this routine NEVER persists that external
    checkpoint and cannot prove that caller input is independently trusted.
    """
    if (type(expected_challenge) is not str
            or HEX32.fullmatch(expected_challenge) is None):
        raise ValueError("Trusted challenge malformed")
    if (type(independently_consumed_nonces) is not frozenset
            or len(independently_consumed_nonces) > 256
            or any(type(item) is not str or HEX32.fullmatch(item) is None
                   for item in independently_consumed_nonces)):
        raise ValueError("Malformed independent consumed-challenge checkpoint")
    if expected_challenge in independently_consumed_nonces:
        raise ValueError("External checkpoint marks challenge consumed")
    # Independently validate the caller's current anchor and operator key;
    # never choose a proposed key from untrusted request JSON.
    old_key_fp = _validate_anchor(trusted_verifier_anchor)
    operator_key_fp = key_fingerprint(trusted_operator_public_key)
    if operator_key_fp == old_key_fp:
        raise ValueError("Operator and verifier roles must be distinct")
    if (type(expected_device_id) is not str
            or DEVICE.fullmatch(expected_device_id) is None
            or type(now_unix) is not int or now_unix < 0):
        raise ValueError("Invalid trusted device or clock")
    _begin(db)
    try:
        row = db.execute(
            """SELECT device_id, old_epoch, old_fingerprint, new_fingerprint,
                      rotation_sha256, operator_fingerprint, issued_unix,
                      expires_unix, consumed_unix
               FROM candidate_operator_challenges WHERE challenge = ?""",
            (expected_challenge,),
        ).fetchone()
        if row is None or row[8] is not None:
            raise ValueError("Operator challenge missing or already consumed")
        device, old_epoch, old_fp, new_fp, rotation_fp, operator_fp, issued, expiry, _ = row
        if (device != expected_device_id
                or new_fp == old_key_fp
                or new_fp == operator_key_fp
                or new_fp in trusted_verifier_anchor.revoked_fingerprints
                or old_epoch != trusted_verifier_anchor.epoch
                or old_fp != key_fingerprint(trusted_verifier_anchor.public_key)
                or operator_fp != key_fingerprint(trusted_operator_public_key)
                or type(issued) is not int or type(expiry) is not int
                or not issued <= now_unix < expiry):
            raise ValueError("Operator challenge context, identity or time mismatch")
        # The review validates the separate operator's Ed25519 signature and
        # BOTH old/new verifier signatures bound to exact proposal digest.
        review = inspect_operator_review(
            operator_envelope, rotation_envelope,
            trusted_operator_public_key=trusted_operator_public_key,
            trusted_verifier_anchor=trusted_verifier_anchor,
            expected_device_id=expected_device_id,
            expected_operator_challenge=expected_challenge,
            now_unix=now_unix,
        )
        if (review.rotation_sha256 != rotation_fp
                or review.proposed_key_sha256 != new_fp
                or review.old_key_sha256 != old_fp
                or review.old_epoch != old_epoch
                or review.proposed_epoch != old_epoch + 1):
            raise ValueError("Signed operator review differs from issued challenge")
        updated = db.execute(
            """UPDATE candidate_operator_challenges SET consumed_unix = ?
               WHERE challenge = ? AND consumed_unix IS NULL""",
            (now_unix, expected_challenge),
        )
        if updated.rowcount != 1:
            raise ValueError("Concurrent operator challenge replay")
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return InspectedOperatorReview(
        challenge=expected_challenge, device_id=expected_device_id,
        old_epoch=old_epoch, proposed_epoch=review.proposed_epoch,
        rotation_sha256=rotation_fp,
    )
