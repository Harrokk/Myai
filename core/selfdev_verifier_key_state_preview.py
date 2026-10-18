"""OFF-DEVICE ONLY: SQLite candidate verifier key-state / revocation simulation.

Does NOT provision signing keys, authorize operator actions, mutate production
trust anchors, open database paths or implement external rollback protection.
The updater MUST supply its separately trusted *exact* key+epoch+revocations
checkpoint; restoring an older DB is detectable ONLY if that checkpoint is
maintained and advanced somewhere independently protected.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

from core.selfdev_verifier_key_rotation import (
    TrustedVerifierKey, _validate_anchor, inspect_rotation, key_fingerprint,
)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS candidate_verifier_state (
       singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
       epoch INTEGER NOT NULL CHECK (epoch > 0 AND epoch < 2147483648),
       public_key BLOB NOT NULL CHECK (length(public_key) = 32),
       fingerprint TEXT NOT NULL CHECK (length(fingerprint) = 64)
    )""",
    """CREATE TABLE IF NOT EXISTS candidate_verifier_revoked (
       fingerprint TEXT PRIMARY KEY NOT NULL CHECK (length(fingerprint) = 64),
       retired_at_epoch INTEGER NOT NULL CHECK (retired_at_epoch > 1)
    )""",
    """CREATE TABLE IF NOT EXISTS candidate_verifier_transitions (
       id INTEGER PRIMARY KEY,
       old_epoch INTEGER NOT NULL,
       new_epoch INTEGER NOT NULL UNIQUE,
       old_fingerprint TEXT NOT NULL,
       new_fingerprint TEXT NOT NULL,
       transition_sha256 TEXT NOT NULL UNIQUE,
       operator_nonce TEXT NOT NULL UNIQUE,
       observed_unix INTEGER NOT NULL
    )""",
)


@dataclass(frozen=True)
class CandidateSnapshot:
    epoch: int
    fingerprint: str
    retired_fingerprints: frozenset[str]
    independently_pinned_checkpoint_matched: bool = True
    real_key_provisioning_verified: bool = False
    storage_rollback_resistance_verified: bool = False
    actual_key_rotation_performed: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


@dataclass(frozen=True)
class CandidateTransition:
    old_epoch: int
    new_epoch: int
    old_fingerprint: str
    new_fingerprint: str
    old_key_retired_in_candidate_database: bool = True
    candidate_sqlite_transaction_committed: bool = True
    independent_operator_authentication_verified: bool = False
    independent_monotonic_checkpoint_updated: bool = False
    actual_key_rotation_performed: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _begin(db):
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ValueError("Separate updater SQLite connection without pending transaction required")
    db.execute("BEGIN IMMEDIATE")


def initialize_candidate_schema(db):
    """Schema changes on caller's explicit disposable test connection only."""
    _begin(db)
    try:
        for statement in _SCHEMA:
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def seed_candidate_for_test(db, *, externally_pinned_initial_key):
    """Explicit test-only bootstrap; refuse importing runtime-supplied keys."""
    anchor = externally_pinned_initial_key
    fingerprint = _validate_anchor(anchor)
    if anchor.revoked_fingerprints:
        raise ValueError("Bootstrap with revocations requires separate trusted recovery")
    _begin(db)
    try:
        if db.execute("SELECT COUNT(*) FROM candidate_verifier_state").fetchone()[0]:
            raise ValueError("Candidate trust anchor already bootstrapped")
        db.execute(
            """INSERT INTO candidate_verifier_state
               (singleton, epoch, public_key, fingerprint) VALUES (1, ?, ?, ?)""",
            (anchor.epoch, anchor.public_key, fingerprint),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return CandidateSnapshot(anchor.epoch, fingerprint, frozenset())


def _matched_state(db, independently_pinned_checkpoint):
    checkpoint = independently_pinned_checkpoint
    _validate_anchor(checkpoint)
    row = db.execute(
        """SELECT epoch, public_key, fingerprint FROM candidate_verifier_state
           WHERE singleton=1"""
    ).fetchone()
    if row is None:
        raise ValueError("Candidate verifier anchor missing")
    epoch, public_key, fingerprint = row
    if (type(epoch) is not int or type(public_key) is not bytes
            or type(fingerprint) is not str or
            epoch != checkpoint.epoch or public_key != checkpoint.public_key
            or fingerprint != key_fingerprint(public_key)):
        raise ValueError("Candidate DB does not match independent key/epoch checkpoint")
    rows = db.execute(
        "SELECT fingerprint FROM candidate_verifier_revoked ORDER BY fingerprint"
    ).fetchall()
    revoked = frozenset(item[0] for item in rows)
    if (len(revoked) != len(rows) or len(revoked) > 256
            or any(type(item) is not str for item in revoked)
            or fingerprint in revoked):
        raise ValueError("Candidate revocation state invalid")
    if revoked != checkpoint.revoked_fingerprints:
        raise ValueError("Candidate revocations disagree with independent checkpoint")
    return TrustedVerifierKey(public_key, epoch, revoked), fingerprint


def inspect_candidate_snapshot(db, *, independently_pinned_checkpoint):
    """Read-only and fail-closed against a trusted external exact checkpoint."""
    if not isinstance(db, sqlite3.Connection):
        raise ValueError("SQLite connection required")
    anchor, fingerprint = _matched_state(db, independently_pinned_checkpoint)
    return CandidateSnapshot(anchor.epoch, fingerprint, anchor.revoked_fingerprints)


def simulate_candidate_transition(
    db, *, independently_pinned_checkpoint, signed_envelope,
    expected_operator_nonce, independently_approved_payload_sha256, now_unix,
):
    """Atomic candidate DB update only; NO real trust-anchor activation.

    Even a committed synthetic transition never updates an external
    checkpoint or proves independent operator authentication.
    """
    if type(now_unix) is not int or now_unix < 0:
        raise ValueError("Trusted simulation clock required")
    _begin(db)
    try:
        anchor, old_fingerprint = _matched_state(db, independently_pinned_checkpoint)
        receipt = inspect_rotation(
            signed_envelope, pinned_key=anchor,
            expected_operator_nonce=expected_operator_nonce,
            independently_approved_payload_sha256=independently_approved_payload_sha256,
            now_unix=now_unix,
        )
        # This payload was already strict-parsed, signed, and context checked
        # by inspect_rotation; no envelope-provided trust anchor is accepted.
        new_public_key = bytes.fromhex(
            json.loads(signed_envelope)["statement"]["new_key_hex"]
        )
        new_fingerprint = key_fingerprint(new_public_key)
        if new_fingerprint != receipt.proposed_key_sha256:
            raise ValueError("Signed candidate fingerprint drift")
        cursor = db.execute(
            """UPDATE candidate_verifier_state
               SET epoch=?, public_key=?, fingerprint=?
               WHERE singleton=1 AND epoch=? AND public_key=? AND fingerprint=?""",
            (receipt.proposed_epoch, new_public_key, new_fingerprint,
             anchor.epoch, anchor.public_key, old_fingerprint),
        )
        if cursor.rowcount != 1:
            raise ValueError("Candidate changed under concurrent update")
        db.execute(
            """INSERT INTO candidate_verifier_revoked
               (fingerprint, retired_at_epoch) VALUES (?, ?)""",
            (old_fingerprint, receipt.proposed_epoch),
        )
        db.execute(
            """INSERT INTO candidate_verifier_transitions
               (old_epoch, new_epoch, old_fingerprint, new_fingerprint,
                transition_sha256, operator_nonce, observed_unix)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (anchor.epoch, receipt.proposed_epoch, old_fingerprint,
             new_fingerprint, independently_approved_payload_sha256,
             expected_operator_nonce, now_unix),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return CandidateTransition(
        anchor.epoch, receipt.proposed_epoch, old_fingerprint, new_fingerprint,
    )
