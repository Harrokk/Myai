"""OFF-DEVICE signed witness milestone receipt INSPECTION (never an action).

Read-only validation combines a local candidate journal (untrusted), a separately
signed and independently pinned witness chain, and a separately pinned receipt
signer. Neither a signature nor an attested milestone proves a real durable
device write unless the separately provisioned signer independently observed
it. No live signer, private keys, file opening, deployment or recovery here.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import sqlite3

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.selfdev_candidate_crash_intent_journal import _read_locked, INTENT
from core.selfdev_operator_signed_review import DEVICE
from core.selfdev_signed_witness_checkpoint import inspect_witness_chain
from core.selfdev_verifier_key_rotation import key_fingerprint

DOMAIN = b"MyAI/offline/witness-milestone-receipt/v1\0"
ISSUER = "myai-separated-witness-milestone-receipt-v1"
PURPOSE = "inspection-only-observed-checkpoint"
AUDIENCE = "myai-updater-offline-source-inspection"
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX128 = re.compile(r"[0-9a-f]{128}\Z")
MAX_WIRE = 4096
FIELDS = frozenset({
    "version", "issuer", "purpose", "audience",
    "device_id", "intent_id", "stage", "operator_nonce",
    "rotation_sha256", "journal_event_sha256", "witness_head_sha256",
    "witness_sequence", "old_epoch", "new_epoch", "verified_unix",
    "expires_unix",
})
WITNESSED_STAGES = ("operator_witness_recorded", "key_witness_recorded")


@dataclass(frozen=True)
class MilestoneReceiptInspection:
    device_id: str
    intent_id: str
    stage: str
    witness_sequence: int
    witness_head_sha256: str
    receipt_signature_verified: bool = True
    witness_signature_and_pinned_head_verified: bool = True
    journal_event_context_matched: bool = True
    witnessed_nonce_and_epoch_matched: bool = True
    receipt_signer_independent_execution_proven: bool = False
    real_external_write_observed: bool = False
    external_head_freshness_verified: bool = False
    operator_human_intent_verified: bool = False
    automatic_recovery_permitted: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _unique(pairs):
    obj = {}
    for key, value in pairs:
        if key in obj:
            raise ValueError("Duplicate signed receipt JSON key")
        obj[key] = value
    return obj


def _bad_constant(_):
    raise ValueError("Nonfinite receipt value")


def _hex(s, expression, label):
    if type(s) is not str or expression.fullmatch(s) is None:
        raise ValueError("Invalid " + label)
    return s


def canonical_milestone_receipt(record):
    if type(record) is not dict or set(record) != FIELDS:
        raise ValueError("Missing/unknown signed milestone receipt field")
    if type(record["version"]) is not int or record["version"] != 1:
        raise ValueError("Invalid milestone receipt version")
    if (record["issuer"] != ISSUER or record["purpose"] != PURPOSE
            or record["audience"] != AUDIENCE):
        raise ValueError("Wrong receipt signing domain")
    if (type(record["device_id"]) is not str
            or DEVICE.fullmatch(record["device_id"]) is None
            or type(record["intent_id"]) is not str
            or INTENT.fullmatch(record["intent_id"]) is None
            or type(record["stage"]) is not str
            or record["stage"] not in WITNESSED_STAGES):
        raise ValueError("Invalid receipt device/intent/stage")
    for name, regex in (
        ("operator_nonce", HEX32),
        ("rotation_sha256", HEX64),
        ("journal_event_sha256", HEX64),
        ("witness_head_sha256", HEX64),
    ):
        _hex(record[name], regex, name)
    if (type(record["witness_sequence"]) is not int
            or not 2 <= record["witness_sequence"] < 2**31
            or type(record["old_epoch"]) is not int
            or type(record["new_epoch"]) is not int
            or not 1 <= record["old_epoch"] < 2**31-1
            or record["new_epoch"] != record["old_epoch"] + 1):
        raise ValueError("Invalid witness sequence or planned key generation")
    begin, end = record["verified_unix"], record["expires_unix"]
    if (type(begin) is not int or type(end) is not int
            or begin < 0 or not begin < end
            or end - begin > 120):
        raise ValueError("Invalid bounded milestone receipt lifetime")
    return DOMAIN + json.dumps(
        record, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def inspect_signed_witness_milestone(
    *, journal_db, receipt_envelope, witness_envelopes,
    trusted_receipt_public_key, trusted_witness_public_key,
    independently_pinned_genesis_sha256, independently_pinned_latest_sha256,
    expected_device_id, expected_intent_id, now_unix,
):
    """Both signatures, pinned head and local journal must match exact context.

    Authenticates two test signing keys, not the physical fact of a write.
    The caller must protect pinned keys and latest head outside runtime.
    """
    receipt_fp = key_fingerprint(trusted_receipt_public_key)
    if receipt_fp == key_fingerprint(trusted_witness_public_key):
        raise ValueError("Receipt and witness signing keys must be distinct")
    if (type(now_unix) is not int or now_unix < 0
            or type(expected_device_id) is not str
            or DEVICE.fullmatch(expected_device_id) is None
            or type(expected_intent_id) is not str
            or INTENT.fullmatch(expected_intent_id) is None):
        raise ValueError("Invalid trusted clock/device/intent")
    if type(receipt_envelope) is not bytes or not 0 < len(receipt_envelope) <= MAX_WIRE:
        raise ValueError("Invalid receipt envelope size/type")
    try:
        envelope = json.loads(
            receipt_envelope.decode("utf-8"),
            object_pairs_hook=_unique,
            parse_constant=_bad_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as exc:
        raise ValueError("Malformed milestone receipt envelope") from exc
    if type(envelope) is not dict or set(envelope) != {"statement", "signature"}:
        raise ValueError("Unexpected signed receipt envelope layout")
    statement = envelope["statement"]
    signed = canonical_milestone_receipt(statement)
    sig = _hex(envelope["signature"], HEX128, "receipt signature")
    if (statement["device_id"] != expected_device_id
            or statement["intent_id"] != expected_intent_id
            or not statement["verified_unix"] <= now_unix < statement["expires_unix"]):
        raise ValueError("Receipt device/intent/time mismatch")
    try:
        Ed25519PublicKey.from_public_bytes(trusted_receipt_public_key).verify(
            bytes.fromhex(sig), signed,
        )
    except (InvalidSignature, ValueError) as exc:
        raise ValueError("Invalid independently pinned receipt signature") from exc
    witness = inspect_witness_chain(
        witness_envelopes,
        trusted_witness_public_key=trusted_witness_public_key,
        independently_pinned_genesis_sha256=independently_pinned_genesis_sha256,
        independently_pinned_latest_sha256=independently_pinned_latest_sha256,
        expected_device_id=expected_device_id,
    )
    if (statement["witness_head_sha256"] != witness.checkpoint_sha256
            or statement["witness_sequence"] != witness.sequence
            or statement["operator_nonce"] not in witness.consumed_operator_nonces):
        raise ValueError("Receipt not bound to witnessed head, sequence and nonce")
    if (not isinstance(journal_db, sqlite3.Connection)
            or journal_db.in_transaction):
        raise ValueError("Expected separate idle candidate journal connection")
    journal_db.execute("BEGIN")
    try:
        device, nonce, old, new, event, intermediate, final = _read_locked(
            journal_db, expected_intent_id,
        )
        rotation = journal_db.execute(
            "SELECT expected_rotation_sha256 FROM candidate_crash_intents WHERE intent_id=?",
            (expected_intent_id,),
        ).fetchone()
    except sqlite3.Error as exc:
        raise ValueError("Missing or malformed candidate journal tables") from exc
    finally:
        journal_db.rollback()
    if rotation is None or len(rotation) != 1:
        raise ValueError("Missing candidate rotation context")
    stage_idx, stage, observed_head, _, event_digest = event
    if (device != expected_device_id or nonce != statement["operator_nonce"]
            or rotation[0] != statement["rotation_sha256"]
            or old != statement["old_epoch"] or new != statement["new_epoch"]
            or stage != statement["stage"]
            or event_digest != statement["journal_event_sha256"]
            or stage_idx not in (2, 4)
            or observed_head != witness.checkpoint_sha256):
        raise ValueError("Signed receipt does not match validated journal state")
    if stage_idx == 2:
        if (intermediate != witness.checkpoint_sha256
                or witness.verifier_epoch != old):
            raise ValueError("Intermediate witnessed nonce state wrong")
    elif stage_idx == 4:
        # A signed valid witness chain has separately checked epoch progression,
        # but genesis and current epochs must also match this exact intent.
        first = witness_envelopes[0]
        try:
            genesis = json.loads(first.decode("utf-8"), object_pairs_hook=_unique)
            original = genesis["statement"]
        except (UnicodeError, ValueError, TypeError, KeyError) as exc:
            raise ValueError("Missing witness genesis for intent") from exc
        if (final != witness.checkpoint_sha256
                or witness.verifier_epoch != new
                or type(original) is not dict
                or original.get("verifier_epoch") != old
                or original.get("verifier_fingerprint")
                    not in witness.retired_verifier_fingerprints):
            raise ValueError("Final witnessed key retirement not proven by chain")
    return MilestoneReceiptInspection(
        device_id=device,
        intent_id=expected_intent_id,
        stage=stage,
        witness_sequence=witness.sequence,
        witness_head_sha256=witness.checkpoint_sha256,
    )
