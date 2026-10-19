"""Source-only issuer policy regressions; ephemeral keys and SQLite only."""
from pathlib import Path
from dataclasses import FrozenInstanceError
import hashlib
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_receipt_issuer_preview import inspect_candidate_for_receipt
from core.selfdev_signed_witness_milestone import canonical_milestone_receipt
from core.selfdev_candidate_crash_intent_journal import (
    initialize_candidate_intent_journal, create_candidate_intent,
    record_candidate_milestone, STAGES,
)
from core.selfdev_signed_witness_checkpoint import (
    ISSUER, PURPOSE, AUDIENCE, canonical_witness_checkpoint,
)

DEVICE = "hosted_receipt_fixture"
INTENT = "synthetic_receipt_intent"
NONCE = "b" * 32
ROTATION = "a" * 64
NOW = 1_800_000_000


def keys():
    private = Ed25519PrivateKey.generate()
    pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, pub


def signed(private, public, epoch, seq, parent, *, consumed=(), retired=()):
    body = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "device_id": DEVICE,
        "sequence": seq, "verifier_epoch": epoch,
        "verifier_public_key_hex": public.hex(),
        "verifier_fingerprint": hashlib.sha256(public).hexdigest(),
        "retired_verifier_fingerprints": sorted(retired),
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": parent,
        "recorded_unix": NOW + seq,
    }
    canon = canonical_witness_checkpoint(body)
    wire = json.dumps({
        "statement": body, "signature": private.sign(canon).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return wire, hashlib.sha256(canon).hexdigest()


@pytest.fixture
def lab(tmp_path):
    witness_secret, witness_public = keys()
    _, old_pub = keys()
    _, new_pub = keys()
    gen, gen_id = signed(witness_secret, old_pub, 4, 1, "0"*64)
    mid, mid_id = signed(
        witness_secret, old_pub, 4, 2, gen_id, consumed=(NONCE,),
    )
    final, final_id = signed(
        witness_secret, new_pub, 5, 3, mid_id, consumed=(NONCE,),
        retired=(hashlib.sha256(old_pub).hexdigest(),),
    )
    db = sqlite3.connect(tmp_path / "synthetic_issuer.sqlite")
    initialize_candidate_intent_journal(db)
    create_candidate_intent(
        db, intent_id=INTENT, device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION,
        expected_operator_witness_head=mid_id,
        expected_final_witness_head=final_id,
        created_unix=NOW-10,
    )
    yield {
        "db": db, "witness_pub": witness_public,
        "wires": [gen, mid, final],
        "heads": [gen_id, mid_id, final_id],
    }
    db.close()


def call(lab, last=1, **override):
    args = dict(
        private_journal_db=lab["db"],
        witness_envelopes=lab["wires"][:last+1],
        pinned_witness_public_key=lab["witness_pub"],
        pinned_genesis_sha256=lab["heads"][0],
        pinned_latest_sha256=lab["heads"][last],
        expected_device_id=DEVICE, expected_intent_id=INTENT,
        trusted_now_unix=NOW,
    )
    args.update(override)
    return inspect_candidate_for_receipt(**args)


def advance(lab, end):
    for idx in range(1, end+1):
        record_candidate_milestone(
            lab["db"], intent_id=INTENT, next_stage=STAGES[idx],
            observed_witness_head=lab["heads"][1] if idx == 2
            else lab["heads"][2] if idx == 4 else "0"*64,
        )


@pytest.mark.parametrize("last", [1, 2])
def test_issuer_derives_receipt_from_real_signed_witness_and_journal(lab, last):
    advance(lab, 2 if last == 1 else 4)
    inspected = call(lab, last)
    stmt = inspected.statement
    assert stmt["stage"] == STAGES[2 if last == 1 else 4]
    assert stmt["witness_head_sha256"] == lab["heads"][last]
    assert stmt["witness_sequence"] == last+1
    assert stmt["operator_nonce"] == NONCE
    assert stmt["rotation_sha256"] == ROTATION
    assert len(canonical_milestone_receipt(stmt)) > 50
    assert inspected.signed_witness_chain_verified
    assert inspected.source_journal_current_event_checked
    assert not inspected.independently_observed_external_write
    assert not inspected.independently_protected_fresh_head_proven
    assert not inspected.signing_key_custody_verified
    assert not inspected.automatic_recovery_authorized
    assert not inspected.production_deployment_authorized
    with pytest.raises(FrozenInstanceError):
        inspected.production_deployment_authorized = True


@pytest.mark.parametrize("last", [0, 1, 2])
def test_unwitnessed_journal_stages_cannot_become_receipts(lab, last):
    advance(lab, 1)
    with pytest.raises(ValueError):
        call(lab, last)


@pytest.mark.parametrize("change", [
    "wrong_witness_key", "wrong_head", "wrong_device",
    "wrong_intent", "missing_nonce", "tampered_witness",
    "expired_genesis_chain", "unauthorized_journal_advance",
])
def test_false_or_stale_provenance_is_never_signable(lab, change):
    advance(lab, 2)
    override = {}
    if change == "wrong_witness_key":
        override["pinned_witness_public_key"] = keys()[1]
    elif change == "wrong_head":
        override["pinned_latest_sha256"] = lab["heads"][2]
    elif change == "wrong_device":
        override["expected_device_id"] = "another_device"
    elif change == "wrong_intent":
        override["expected_intent_id"] = "another_intent"
    elif change == "missing_nonce":
        override["witness_envelopes"] = lab["wires"][:1]
    elif change == "tampered_witness":
        forged = list(lab["wires"][:2])
        x = json.loads(forged[1])
        x["signature"] = "f"*128
        forged[1] = json.dumps(x).encode()
        override["witness_envelopes"] = forged
    elif change == "expired_genesis_chain":
        override["pinned_genesis_sha256"] = "f"*64
    elif change == "unauthorized_journal_advance":
        record_candidate_milestone(
            lab["db"], intent_id=INTENT, next_stage=STAGES[3],
        )
    with pytest.raises(ValueError):
        call(lab, **override)


def test_no_unauthenticated_external_receipt_signing_or_writes():
    import core.selfdev_receipt_issuer_preview as module
    source = Path(module.__file__).read_text()
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager", "os.chown(",
        "UPDATE ", "INSERT INTO", "DELETE FROM",
    ):
        assert forbidden not in source
    assert "independently_observed_external_write: bool = False" in source
    assert "production_deployment_authorized: bool = False" in source
