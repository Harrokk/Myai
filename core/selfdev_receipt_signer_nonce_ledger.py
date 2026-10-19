"""Signer-owned *candidate* SQLite single-use receipt challenge ledger.

This is a test-only primitive used by an independently isolated test signer
AFTER inspecting a signed witness head. It persists consumed nonces across
SQLite reopen and uses BEGIN IMMEDIATE for a single winner, but cannot prove
physical power-loss durability, independently protected monotonic head or
root/same-UID resistance. It does not generate secrets, sign, install or deploy.
"""
from __future__ import annotations

from dataclasses import dataclass
import re
import sqlite3

from core.selfdev_candidate_crash_intent_journal import INTENT
from core.selfdev_operator_signed_review import DEVICE

HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
_SCHEMA = """CREATE TABLE IF NOT EXISTS candidate_signer_consumed_receipts (
  challenge TEXT PRIMARY KEY CHECK(length(challenge)=32),
  device_id TEXT NOT NULL,
  intent_id TEXT NOT NULL,
  signed_witness_head_sha256 TEXT NOT NULL,
  journal_event_sha256 TEXT NOT NULL,
  consumed_unix INTEGER NOT NULL CHECK(consumed_unix>=0),
  expires_unix INTEGER NOT NULL CHECK(expires_unix>consumed_unix),
  CHECK(expires_unix-consumed_unix<=120)
)"""


@dataclass(frozen=True)
class SignerConsumedChallenge:
    challenge: str
    device_id: str
    intent_id: str
    witness_head_sha256: str
    signer_owned_candidate_recorded: bool = True
    actual_receipt_delivered: bool = False
    independent_external_checkpoint_advanced: bool = False
    power_loss_rollback_resistance_verified: bool = False
    production_deployment_authorized: bool = False
    authorizes_mutation: bool = False


def _begin(db):
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ValueError("Independent signer-owned idle SQLite connection required")
    db.execute("BEGIN IMMEDIATE")


def initialize_signer_candidate_nonce_ledger(db):
    _begin(db)
    try:
        db.execute(_SCHEMA)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def claim_receipt_once(
    db, *, challenge, device_id, intent_id, signed_witness_head_sha256,
    journal_event_sha256, now_unix, expires_unix,
):
    """Commit nonce CONSUMED before signing; failure after commit stays blocked.

    Caller must have independently inspected the witness and journal and
    controlled the DB/UID. None of that is provable from this function itself.
    """
    if (type(challenge) is not str or HEX32.fullmatch(challenge) is None
            or type(device_id) is not str or DEVICE.fullmatch(device_id) is None
            or type(intent_id) is not str or INTENT.fullmatch(intent_id) is None
            or type(signed_witness_head_sha256) is not str
            or HEX64.fullmatch(signed_witness_head_sha256) is None
            or type(journal_event_sha256) is not str
            or HEX64.fullmatch(journal_event_sha256) is None
            or type(now_unix) is not int or type(expires_unix) is not int
            or now_unix < 0 or not now_unix < expires_unix
            or expires_unix - now_unix > 120):
        raise ValueError("Invalid strictly bounded signer witness challenge context")
    _begin(db)
    try:
        # Not an UPSERT. A repeated challenge is terminally denied,
        # even when the caller supplies changed event/head or new key.
        previous = db.execute(
            "SELECT challenge FROM candidate_signer_consumed_receipts WHERE challenge=?",
            (challenge,),
        ).fetchone()
        if previous is not None:
            raise ValueError("Signer challenge already consumed")
        db.execute(
            """INSERT INTO candidate_signer_consumed_receipts
               (challenge, device_id, intent_id, signed_witness_head_sha256,
                journal_event_sha256, consumed_unix, expires_unix)
               VALUES (?,?,?,?,?,?,?)""",
            (challenge, device_id, intent_id, signed_witness_head_sha256,
             journal_event_sha256, now_unix, expires_unix),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return SignerConsumedChallenge(
        challenge, device_id, intent_id, signed_witness_head_sha256,
    )
