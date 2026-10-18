"""OFF-DEVICE recovery consistency INSPECTION; no recovery execution.

Checks two independently read SQLite candidate snapshots against a separately
signed and caller-pinned witness history. A consistent result is NOT an
authorization to advance, release, promote, repair, or resume execution.

WARNING: two SQLite connections and an external witness are not a distributed
atomic snapshot. The caller must quiesce all writers and independently protect
the witness signing key and pinned latest-head digest. Neither is implemented.
"""
from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from core.selfdev_operator_signed_review import DEVICE
from core.selfdev_signed_witness_checkpoint import inspect_witness_chain
from core.selfdev_verifier_key_rotation import key_fingerprint

MAX_LOCAL_CHALLENGES = 256


@dataclass(frozen=True)
class RecoveryInspection:
    device_id: str
    witness_head_sha256: str
    witness_sequence: int
    witness_verifier_epoch: int
    candidate_verifier_epoch: int
    differences: tuple[str, ...]
    candidate_views_equal_signed_witness: bool
    manual_reconciliation_required: bool
    independent_live_head_freshness_verified: bool = False
    concurrent_writers_quiesced_verified: bool = False
    cross_database_atomic_snapshot_verified: bool = False
    external_durable_commit_verified: bool = False
    automatic_repair_permitted: bool = False
    safe_to_resume_production: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _read_candidate_key(db):
    records = db.execute(
        "SELECT epoch, public_key, fingerprint FROM candidate_verifier_state"
    ).fetchall()
    if len(records) != 1:
        raise ValueError("Candidate verifier state must have exactly one row")
    epoch, public_key, fingerprint = records[0]
    if (type(epoch) is not int or not 1 <= epoch < 2**31
            or type(public_key) is not bytes
            or type(fingerprint) is not str
            or key_fingerprint(public_key) != fingerprint):
        raise ValueError("Corrupt candidate verifier state")
    revoked_rows = db.execute(
        "SELECT fingerprint FROM candidate_verifier_revoked ORDER BY fingerprint"
    ).fetchall()
    if len(revoked_rows) > 256:
        raise ValueError("Candidate revoked set exceeds reviewed limit")
    revoked = frozenset(row[0] for row in revoked_rows)
    if (len(revoked) != len(revoked_rows)
            or any(type(item) is not str or len(item) != 64
                   or any(ch not in "0123456789abcdef" for ch in item)
                   for item in revoked)
            or fingerprint in revoked):
        raise ValueError("Corrupt candidate verifier revocations")
    return epoch, public_key, fingerprint, revoked


def _read_consumed_nonces(db, expected_device_id):
    rows = db.execute(
        """SELECT challenge, device_id, issued_unix, expires_unix,
                  consumed_unix FROM candidate_operator_challenges
           ORDER BY challenge"""
    ).fetchall()
    if len(rows) > MAX_LOCAL_CHALLENGES:
        raise ValueError("Candidate operator history exceeds reviewed limit")
    seen = set()
    consumed = set()
    for nonce, device, issued, expiry, used in rows:
        if (type(nonce) is not str or len(nonce) != 32
                or any(ch not in "0123456789abcdef" for ch in nonce)
                or nonce in seen or device != expected_device_id
                or type(issued) is not int or type(expiry) is not int
                or not 0 <= issued < expiry
                or expiry - issued > 300
                or (used is not None
                    and (type(used) is not int or used < issued))):
            raise ValueError("Invalid, duplicate or cross-device operator challenge")
        seen.add(nonce)
        if used is not None:
            consumed.add(nonce)
    return frozenset(consumed)


def inspect_recovery_consistency(
    *, candidate_key_db, candidate_operator_db,
    witness_envelopes, pinned_witness_public_key,
    pinned_genesis_sha256, pinned_latest_head_sha256, expected_device_id,
):
    """Fail closed on a corrupt witness or a malformed local database.

    A successful comparison can only report *candidate agreement*, never
    recover or transition live trust: signed old heads remain replayable
    whenever independently pinned latest head can also be rolled back.
    """
    if (not isinstance(candidate_key_db, sqlite3.Connection)
            or not isinstance(candidate_operator_db, sqlite3.Connection)
            or candidate_key_db is candidate_operator_db
            or candidate_key_db.in_transaction
            or candidate_operator_db.in_transaction):
        raise ValueError("Two separate idle caller-owned SQLite connections required")
    if (type(expected_device_id) is not str
            or DEVICE.fullmatch(expected_device_id) is None):
        raise ValueError("Expected trusted device ID required")
    witness = inspect_witness_chain(
        witness_envelopes,
        trusted_witness_public_key=pinned_witness_public_key,
        independently_pinned_genesis_sha256=pinned_genesis_sha256,
        independently_pinned_latest_sha256=pinned_latest_head_sha256,
        expected_device_id=expected_device_id,
    )
    opened = []
    try:
        for db in (candidate_key_db, candidate_operator_db):
            db.execute("BEGIN")
            opened.append(db)
        epoch, public, fingerprint, retired = _read_candidate_key(candidate_key_db)
        consumed = _read_consumed_nonces(candidate_operator_db, expected_device_id)
    except sqlite3.Error as exc:
        raise ValueError("Required candidate database missing/corrupt") from exc
    finally:
        for db in reversed(opened):
            db.rollback()

    problems = []
    if epoch < witness.verifier_epoch:
        problems.append("candidate_key_epoch_behind_witness")
    elif epoch > witness.verifier_epoch:
        problems.append("candidate_key_epoch_ahead_of_witness")
    if (public != witness.verifier_public_key
            or fingerprint != witness.verifier_fingerprint):
        problems.append("candidate_verifier_identity_differs_from_witness")
    if retired != witness.retired_verifier_fingerprints:
        problems.append("candidate_revocations_differ_from_witness")
    if consumed - witness.consumed_operator_nonces:
        problems.append("candidate_consumptions_not_witnessed")
    if witness.consumed_operator_nonces - consumed:
        problems.append("witnessed_consumptions_missing_from_candidate")
    return RecoveryInspection(
        device_id=expected_device_id,
        witness_head_sha256=witness.checkpoint_sha256,
        witness_sequence=witness.sequence,
        witness_verifier_epoch=witness.verifier_epoch,
        candidate_verifier_epoch=epoch,
        differences=tuple(problems),
        candidate_views_equal_signed_witness=not problems,
        manual_reconciliation_required=bool(problems),
    )
