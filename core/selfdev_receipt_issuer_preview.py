"""OFFLINE candidate-only assembly of a would-be independently observed receipt.

No signer, private key, files opened, service, or production authorization.
Only a separately protected service may supply the *real* pinned witness key
and fresh head. This function cannot prove freshness or a real disk write.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import sqlite3

from core.selfdev_candidate_crash_intent_journal import _read_locked, INTENT
from core.selfdev_operator_signed_review import DEVICE
from core.selfdev_signed_witness_checkpoint import inspect_witness_chain
from core.selfdev_signed_witness_milestone import (
    ISSUER, PURPOSE, AUDIENCE, canonical_milestone_receipt,
)


@dataclass(frozen=True)
class InspectedCandidateForReceipt:
    statement: dict
    source_journal_current_event_checked: bool = True
    signed_witness_chain_verified: bool = True
    independently_observed_external_write: bool = False
    independently_protected_fresh_head_proven: bool = False
    signing_key_custody_verified: bool = False
    automatic_recovery_authorized: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def inspect_candidate_for_receipt(
    *, private_journal_db, witness_envelopes,
    pinned_witness_public_key, pinned_genesis_sha256, pinned_latest_sha256,
    expected_device_id, expected_intent_id, trusted_now_unix,
):
    """Assemble only after independently inspecting both witness and journal.

    The caller cannot supply passed/status/receipt stage or output digests.
    The inspected source journal must be owned/protected by the calling service;
    that ownership is NOT verifiable from a SQLite Connection object.
    """
    if (type(trusted_now_unix) is not int or trusted_now_unix < 0
            or type(expected_device_id) is not str
            or DEVICE.fullmatch(expected_device_id) is None
            or type(expected_intent_id) is not str
            or INTENT.fullmatch(expected_intent_id) is None
            or not isinstance(private_journal_db, sqlite3.Connection)
            or private_journal_db.in_transaction):
        raise ValueError("Trusted context and idle private journal connection required")
    witness = inspect_witness_chain(
        witness_envelopes,
        trusted_witness_public_key=pinned_witness_public_key,
        independently_pinned_genesis_sha256=pinned_genesis_sha256,
        independently_pinned_latest_sha256=pinned_latest_sha256,
        expected_device_id=expected_device_id,
    )
    private_journal_db.execute("BEGIN")
    try:
        device, nonce, old, new, event, intermediate, final = _read_locked(
            private_journal_db, expected_intent_id,
        )
        rotation = private_journal_db.execute(
            """SELECT expected_rotation_sha256 FROM candidate_crash_intents
               WHERE intent_id=?""", (expected_intent_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Missing or invalid candidate journal tables") from exc
    finally:
        private_journal_db.rollback()
    if rotation is None or len(rotation) != 1:
        raise ValueError("Missing exact planned rotation digest")
    idx, stage, observed_head, _, event_digest = event
    if (device != expected_device_id
            or idx not in (2, 4)
            or observed_head != witness.checkpoint_sha256
            or nonce not in witness.consumed_operator_nonces):
        raise ValueError("Only real signed witness milestones are inspectable")
    if idx == 2:
        if (intermediate != witness.checkpoint_sha256
                or witness.verifier_epoch != old):
            raise ValueError("Intermediate witnessed operator nonce mismatch")
    else:
        if (final != witness.checkpoint_sha256 or witness.verifier_epoch != new
                or type(witness_envelopes) not in (list, tuple)
                or not witness_envelopes):
            raise ValueError("Final witness epoch/head mismatch")
        try:
            raw = json.loads(witness_envelopes[0].decode("utf-8"))
            original_fp = raw["statement"]["verifier_fingerprint"]
            original_epoch = raw["statement"]["verifier_epoch"]
        except (ValueError, TypeError, UnicodeError, KeyError) as exc:
            raise ValueError("Invalid witness genesis context") from exc
        if (type(original_epoch) is not int
                or original_epoch != old
                or type(original_fp) is not str
                or original_fp not in witness.retired_verifier_fingerprints):
            raise ValueError("Original verifier key not retired at final checkpoint")
    record = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "device_id": expected_device_id,
        "intent_id": expected_intent_id, "stage": stage,
        "operator_nonce": nonce, "rotation_sha256": rotation[0],
        "journal_event_sha256": event_digest,
        "witness_head_sha256": witness.checkpoint_sha256,
        "witness_sequence": witness.sequence,
        "old_epoch": old, "new_epoch": new,
        "verified_unix": trusted_now_unix,
        "expires_unix": trusted_now_unix + 60,
    }
    canonical_milestone_receipt(record)
    return InspectedCandidateForReceipt(record)
