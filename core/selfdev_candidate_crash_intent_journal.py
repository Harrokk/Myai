"""OFF-DEVICE candidate-only crash intent journal; NEVER recovery authorization.

A third caller-owned SQLite DB records an append-only sequence of *claimed*
milestones across the separate nonce/key DBs and witness. SHA256 links detect
accidental corruption, NOT attacker-controlled rollback or forged milestones.
No stage proves a real external write. The real signed witness is checked
separately by PR #344's inspector, never by trusting journal flags.

No file opener, signer, key activation, hardware, service, repair or promotion.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3

from core.selfdev_operator_signed_review import DEVICE

HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
INTENT = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
STAGES = (
    "prepared", "operator_db_recorded", "operator_witness_recorded",
    "key_db_recorded", "key_witness_recorded",
)
DOMAIN = b"MyAI/offline/candidate-crash-intent/v1\0"
MAX_EVENTS = len(STAGES)

_SCHEMA = (
    """CREATE TABLE IF NOT EXISTS candidate_crash_intents (
        intent_id TEXT PRIMARY KEY,
        device_id TEXT NOT NULL,
        operator_nonce TEXT NOT NULL UNIQUE,
        expected_old_epoch INTEGER NOT NULL,
        expected_new_epoch INTEGER NOT NULL,
        expected_rotation_sha256 TEXT NOT NULL,
        expected_operator_witness_head TEXT NOT NULL,
        expected_final_witness_head TEXT NOT NULL,
        created_unix INTEGER NOT NULL
    )""",
    """CREATE TABLE IF NOT EXISTS candidate_crash_events (
        intent_id TEXT NOT NULL,
        stage_index INTEGER NOT NULL,
        stage TEXT NOT NULL,
        observed_witness_head TEXT NOT NULL,
        previous_event_digest TEXT NOT NULL,
        event_digest TEXT NOT NULL UNIQUE,
        PRIMARY KEY(intent_id, stage_index),
        FOREIGN KEY(intent_id) REFERENCES candidate_crash_intents(intent_id)
    )""",
)


@dataclass(frozen=True)
class CandidateIntentSnapshot:
    intent_id: str
    device_id: str
    operator_nonce: str
    old_epoch: int
    proposed_epoch: int
    recorded_stage: str
    recorded_stage_index: int
    observed_witness_head: str
    recorded_event_digest: str
    journal_chain_consistent: bool = True
    actual_external_milestones_verified: bool = False
    witness_freshness_independently_verified: bool = False
    crash_recovery_automatically_permitted: bool = False
    operator_approval_proven: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


@dataclass(frozen=True)
class IntentRecoveryReview:
    intent_id: str
    recorded_stage: str
    observed_recovery_differences: tuple[str, ...]
    journal_stage_is_externally_proven: bool = False
    signed_witness_consistency_inspected: bool = True
    external_head_freshness_verified: bool = False
    distributed_commit_atomicity_verified: bool = False
    manual_reconciliation_required: bool = True
    automatic_resume_permitted: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _hex(value, pattern, label):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError("Invalid " + label)
    return value


def _connection(db):
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise ValueError("Caller-owned idle SQLite connection required")
    db.execute("PRAGMA foreign_keys=ON")


def _begin(db):
    _connection(db)
    db.execute("BEGIN IMMEDIATE")


def _validate_intent(intent_id, device_id, nonce, old_epoch, new_epoch,
                     rotation_digest, interim_head, final_head, created_unix):
    if type(intent_id) is not str or INTENT.fullmatch(intent_id) is None:
        raise ValueError("Invalid candidate intent id")
    if type(device_id) is not str or DEVICE.fullmatch(device_id) is None:
        raise ValueError("Invalid expected device id")
    _hex(nonce, HEX32, "expected operator nonce")
    for label, value in (("rotation", rotation_digest),
                         ("intermediate witness", interim_head),
                         ("final witness", final_head)):
        _hex(value, HEX64, label)
    if interim_head == final_head:
        raise ValueError("Expected independent witness steps must differ")
    if (type(old_epoch) is not int or type(new_epoch) is not int
            or old_epoch < 1 or new_epoch != old_epoch + 1
            or new_epoch >= 2**31):
        raise ValueError("Invalid expected key epoch change")
    if type(created_unix) is not int or created_unix < 0:
        raise ValueError("Invalid journal time")


def _event_digest(intent, index, phase, head, previous):
    payload = {
        "intent_id": intent, "index": index, "stage": phase,
        "observed_witness_head": head, "previous_event_digest": previous,
    }
    return hashlib.sha256(DOMAIN + json.dumps(
        payload, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")).hexdigest()


def initialize_candidate_intent_journal(db):
    _begin(db)
    try:
        for statement in _SCHEMA:
            db.execute(statement)
        db.commit()
    except BaseException:
        db.rollback()
        raise


def create_candidate_intent(
    db, *, intent_id, device_id, operator_nonce,
    expected_old_epoch, expected_new_epoch, rotation_sha256,
    expected_operator_witness_head, expected_final_witness_head,
    created_unix,
):
    """Write only a *local planning claim* to disposable SQLite."""
    _validate_intent(
        intent_id, device_id, operator_nonce, expected_old_epoch,
        expected_new_epoch, rotation_sha256,
        expected_operator_witness_head, expected_final_witness_head,
        created_unix,
    )
    _begin(db)
    try:
        db.execute(
            """INSERT INTO candidate_crash_intents
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (intent_id, device_id, operator_nonce,
             expected_old_epoch, expected_new_epoch,
             rotation_sha256, expected_operator_witness_head,
             expected_final_witness_head, created_unix),
        )
        first = _event_digest(intent_id, 0, STAGES[0], "0"*64, "0"*64)
        db.execute(
            """INSERT INTO candidate_crash_events VALUES (?,?,?,?,?,?)""",
            (intent_id, 0, STAGES[0], "0"*64, "0"*64, first),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return read_candidate_intent(db, intent_id=intent_id)


def _read_locked(db, intent_id):
    row = db.execute(
        """SELECT device_id, operator_nonce, expected_old_epoch,
                  expected_new_epoch, expected_rotation_sha256,
                  expected_operator_witness_head, expected_final_witness_head,
                  created_unix
           FROM candidate_crash_intents WHERE intent_id = ?""",
        (intent_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Unknown crash intent")
    device, nonce, old, new, rotation, intermediate, final, created = row
    _validate_intent(
        intent_id, device, nonce, old, new, rotation, intermediate,
        final, created,
    )
    events = db.execute(
        """SELECT stage_index, stage, observed_witness_head,
                  previous_event_digest, event_digest
           FROM candidate_crash_events WHERE intent_id=?
           ORDER BY stage_index""", (intent_id,),
    ).fetchall()
    if not 1 <= len(events) <= MAX_EVENTS:
        raise ValueError("Invalid candidate event count")
    prior = "0"*64
    for expected_index, item in enumerate(events):
        index, phase, observed, previous, digest = item
        if (type(index) is not int or index != expected_index
                or type(phase) is not str or phase != STAGES[index]
                or type(previous) is not str or previous != prior):
            raise ValueError("Forked, reordered or missing candidate journal step")
        _hex(observed, HEX64, "observed witness digest")
        _hex(digest, HEX64, "event digest")
        expected_head = (
            intermediate if index == 2 else
            final if index == 4 else "0"*64
        )
        if (observed != expected_head
                or digest != _event_digest(intent_id, index, phase, observed, prior)):
            raise ValueError("Candidate event digest or planned head differs")
        prior = digest
    return (device, nonce, old, new, events[-1], intermediate, final)


def read_candidate_intent(db, *, intent_id):
    if type(intent_id) is not str or INTENT.fullmatch(intent_id) is None:
        raise ValueError("Invalid candidate intent id")
    _connection(db)
    device, nonce, old, new, event, _, _ = _read_locked(db, intent_id)
    return CandidateIntentSnapshot(
        intent_id, device, nonce, old, new,
        event[1], event[0], event[2], event[4],
    )


def record_candidate_milestone(db, *, intent_id, next_stage,
                               observed_witness_head="0"*64):
    """Append one orderly *claimed* stage, never perform that actual stage."""
    if type(intent_id) is not str or INTENT.fullmatch(intent_id) is None:
        raise ValueError("Invalid intent id")
    if type(next_stage) is not str or next_stage not in STAGES[1:]:
        raise ValueError("Invalid next stage")
    _hex(observed_witness_head, HEX64, "claimed witness digest")
    _begin(db)
    try:
        _, _, _, _, previous, intermediate, final = _read_locked(db, intent_id)
        index = previous[0] + 1
        if index >= len(STAGES) or next_stage != STAGES[index]:
            raise ValueError("Reordered, duplicated or skipped candidate stage")
        intended = (
            intermediate if index == 2 else
            final if index == 4 else "0"*64
        )
        if observed_witness_head != intended:
            raise ValueError("Claimed witness head not equal to planned digest")
        digest = _event_digest(
            intent_id, index, next_stage, observed_witness_head, previous[4],
        )
        db.execute(
            "INSERT INTO candidate_crash_events VALUES (?,?,?,?,?,?)",
            (intent_id, index, next_stage, observed_witness_head,
             previous[4], digest),
        )
        db.commit()
    except BaseException:
        db.rollback()
        raise
    return read_candidate_intent(db, intent_id=intent_id)


def inspect_candidate_intent_recovery(
    db, *, intent_id, verified_recovery_inspection,
):
    """Combine recorded *claims* with a PR #344 read-only recovery result.

    A dataclass passed by a caller is NOT a certificate. Even perfect equality
    MUST NEVER permit automatic repair, resuming production or key activation.
    """
    from core.selfdev_recovery_consistency import RecoveryInspection
    if type(verified_recovery_inspection) is not RecoveryInspection:
        raise ValueError("A validated recovery-inspection result is required")
    snapshot = read_candidate_intent(db, intent_id=intent_id)
    recovered = verified_recovery_inspection
    if recovered.device_id != snapshot.device_id:
        raise ValueError("Journal and trusted recovery device differ")
    if (recovered.candidate_verifier_epoch < snapshot.old_epoch
            or recovered.candidate_verifier_epoch > snapshot.proposed_epoch
            or recovered.witness_verifier_epoch < snapshot.old_epoch
            or recovered.witness_verifier_epoch > snapshot.proposed_epoch):
        raise ValueError("Candidate state outside planned epoch bounds")
    # Journal milestone flags are untrusted and NOT verified against a live
    # witness, but contradictory claims must still be surfaced to reviewers.
    row = db.execute(
        """SELECT expected_operator_witness_head, expected_final_witness_head
           FROM candidate_crash_intents WHERE intent_id=?""",
        (intent_id,),
    ).fetchone()
    if row is None:
        raise ValueError("Missing journal intent")
    differences = list(recovered.differences)
    claimed_index = snapshot.recorded_stage_index
    expected_head = (
        row[1] if claimed_index == 4 else
        row[0] if claimed_index in (2, 3) else None
    )
    if (expected_head is not None
            and recovered.witness_head_sha256 != expected_head):
        differences.append("journal_claimed_witness_milestone_not_observed")
    return IntentRecoveryReview(
        intent_id=intent_id, recorded_stage=snapshot.recorded_stage,
        observed_recovery_differences=tuple(differences),
    )
