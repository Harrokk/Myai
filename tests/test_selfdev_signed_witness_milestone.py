"""Test-only Ed25519 keys and temporary SQLite: no live signer or device I/O."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_candidate_crash_intent_journal import (
    create_candidate_intent, initialize_candidate_intent_journal,
    record_candidate_milestone, read_candidate_intent, STAGES,
)
from core.selfdev_signed_witness_checkpoint import (
    ISSUER as W_ISSUER, PURPOSE as W_PURPOSE, AUDIENCE as W_AUDIENCE,
    canonical_witness_checkpoint,
)
from core.selfdev_signed_witness_milestone import (
    DOMAIN, ISSUER, AUDIENCE, PURPOSE,
    MilestoneReceiptInspection, canonical_milestone_receipt,
    inspect_signed_witness_milestone,
)

DEVICE = "synthetic_ventuno_1"
INTENT = "review_attempt_1"
NONCE = "a" * 32
ROTATION = "b" * 64
NOW = 1_800_000_000


def key():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def signed_witness(private, public, epoch, seq, parent, *, consumed=(), retired=()):
    statement = {
        "version": 1, "issuer": W_ISSUER,
        "purpose": W_PURPOSE, "audience": W_AUDIENCE,
        "device_id": DEVICE, "sequence": seq, "verifier_epoch": epoch,
        "verifier_public_key_hex": public.hex(),
        "verifier_fingerprint": hashlib.sha256(public).hexdigest(),
        "retired_verifier_fingerprints": sorted(retired),
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": parent,
        "recorded_unix": NOW + seq,
    }
    signed = canonical_witness_checkpoint(statement)
    wire = json.dumps({
        "statement": statement,
        "signature": private.sign(signed).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return wire, hashlib.sha256(signed).hexdigest()


def receipt_body(lab, *, final):
    journal = lab["journal"]
    if final:
        for index in range(1, 5):
            if read_candidate_intent(journal, intent_id=INTENT).recorded_stage_index < index:
                record_candidate_milestone(
                    journal, intent_id=INTENT, next_stage=STAGES[index],
                    observed_witness_head=lab["heads"][1] if index == 2
                    else lab["heads"][2] if index == 4 else "0"*64,
                )
    else:
        for index in range(1, 3):
            if read_candidate_intent(journal, intent_id=INTENT).recorded_stage_index < index:
                record_candidate_milestone(
                    journal, intent_id=INTENT, next_stage=STAGES[index],
                    observed_witness_head=lab["heads"][1] if index == 2 else "0"*64,
                )
    snapshot = read_candidate_intent(journal, intent_id=INTENT)
    stage = snapshot.recorded_stage
    return {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "device_id": DEVICE, "intent_id": INTENT,
        "stage": stage, "operator_nonce": NONCE,
        "rotation_sha256": ROTATION,
        "journal_event_sha256": snapshot.recorded_event_digest,
        "witness_head_sha256": lab["heads"][2 if final else 1],
        "witness_sequence": 3 if final else 2,
        "old_epoch": 4, "new_epoch": 5,
        "verified_unix": NOW - 10, "expires_unix": NOW + 60,
    }


def wire_receipt(private, body):
    return json.dumps({
        "statement": body,
        "signature": private.sign(canonical_milestone_receipt(body)).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()


@pytest.fixture
def lab(tmp_path):
    witness_secret, witness_pub = key()
    receipt_secret, receipt_pub = key()
    _, old = key()
    _, new = key()
    genesis, genesis_head = signed_witness(
        witness_secret, old, 4, 1, "0"*64,
    )
    middle, middle_head = signed_witness(
        witness_secret, old, 4, 2, genesis_head, consumed=(NONCE,),
    )
    final, final_head = signed_witness(
        witness_secret, new, 5, 3, middle_head,
        consumed=(NONCE,), retired=(hashlib.sha256(old).hexdigest(),),
    )
    conn = sqlite3.connect(tmp_path / "offline-candidate-intent.sqlite")
    initialize_candidate_intent_journal(conn)
    create_candidate_intent(
        conn, intent_id=INTENT, device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION, expected_operator_witness_head=middle_head,
        expected_final_witness_head=final_head, created_unix=NOW-100,
    )
    test = {
        "journal": conn, "receipt_secret": receipt_secret,
        "receipt_pub": receipt_pub, "witness_pub": witness_pub,
        "wires": (genesis, middle, final),
        "heads": (genesis_head, middle_head, final_head),
    }
    yield test
    conn.close()


def inspect(lab, envelope, *, final=False, **changes):
    inputs = {
        "journal_db": lab["journal"], "receipt_envelope": envelope,
        "witness_envelopes": lab["wires"][:3 if final else 2],
        "trusted_receipt_public_key": lab["receipt_pub"],
        "trusted_witness_public_key": lab["witness_pub"],
        "independently_pinned_genesis_sha256": lab["heads"][0],
        "independently_pinned_latest_sha256": lab["heads"][2 if final else 1],
        "expected_device_id": DEVICE, "expected_intent_id": INTENT,
        "now_unix": NOW,
    }
    inputs.update(changes)
    return inspect_signed_witness_milestone(**inputs)


@pytest.mark.parametrize("final", [False, True])
def test_receipt_and_witness_and_journal_agree_without_authorizing(final, lab):
    body = receipt_body(lab, final=final)
    result = inspect(lab, wire_receipt(lab["receipt_secret"], body), final=final)
    assert isinstance(result, MilestoneReceiptInspection)
    assert result.stage == body["stage"]
    assert result.witness_head_sha256 == lab["heads"][2 if final else 1]
    assert result.receipt_signature_verified is True
    assert result.witness_signature_and_pinned_head_verified is True
    assert result.journal_event_context_matched is True
    assert result.witnessed_nonce_and_epoch_matched is True
    assert result.receipt_signer_independent_execution_proven is False
    assert result.real_external_write_observed is False
    assert result.external_head_freshness_verified is False
    assert result.operator_human_intent_verified is False
    assert result.automatic_recovery_permitted is False
    assert result.authorizes_mutation is False
    assert result.production_deployment_authorized is False
    with pytest.raises(FrozenInstanceError):
        result.real_external_write_observed = True


def test_domain_separation_and_canonical_order(lab):
    body = receipt_body(lab, final=False)
    assert canonical_milestone_receipt(body).startswith(DOMAIN)
    assert canonical_milestone_receipt(body) == canonical_milestone_receipt(
        dict(reversed(list(body.items())))
    )


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 0},
    {"issuer": "runtime"}, {"purpose": "promote"},
    {"audience": "myai-main"}, {"stage": "key_db_recorded"},
    {"stage": "prepared"}, {"stage": True},
    {"device_id": "../device"}, {"device_id": ""},
    {"intent_id": ""}, {"intent_id": "../bad"},
    {"operator_nonce": "A"*32}, {"rotation_sha256": "f"*63},
    {"journal_event_sha256": None}, {"witness_head_sha256": "Z"*64},
    {"witness_sequence": True}, {"witness_sequence": 1},
    {"old_epoch": True}, {"old_epoch": 0},
    {"new_epoch": 7}, {"verified_unix": True},
    {"expires_unix": NOW+1000},
    {"expires_unix": NOW-10},
])
def test_invalid_receipt_fields_never_signable(lab, patch):
    body = receipt_body(lab, final=False)
    body.update(patch)
    with pytest.raises(ValueError):
        canonical_milestone_receipt(body)


@pytest.mark.parametrize("extra", [
    "private_key", "operator_consent", "trusted_witness_key",
    "device_path", "promote", "repair", "verified_hardware_write",
])
def test_caller_claims_of_privilege_denied(lab, extra):
    body = receipt_body(lab, final=False)
    body[extra] = True
    with pytest.raises(ValueError):
        canonical_milestone_receipt(body)


@pytest.mark.parametrize("bad", [
    b"", b"\xff", b"{}", b"[]", b"NaN",
    b'{"statement":1,"signature":"0","signature":"0"}',
    b'{"statement":NaN,"signature":"0"}',
    b"z"*4097,
])
def test_invalid_or_duplicate_envelopes_rejected(lab, bad):
    with pytest.raises(ValueError):
        inspect(lab, bad)


@pytest.mark.parametrize("mutation", [
    "receipt_sig", "receipt_signer", "witness_signer",
    "device", "intent", "receipt_nonce", "rotation",
    "event_digest", "head", "sequence", "old_epoch",
    "new_epoch", "expired", "before_valid", "witness_rollback",
    "witness_sig", "wrong_witness_nonce",
])
def test_even_freshly_signed_lie_or_mismatched_trust_is_rejected(lab, mutation):
    body = receipt_body(lab, final=False)
    overrides = {}
    if mutation == "receipt_signer":
        overrides["trusted_receipt_public_key"] = key()[1]
    elif mutation == "witness_signer":
        overrides["trusted_witness_public_key"] = key()[1]
    elif mutation == "device":
        body["device_id"] = "other_device"
    elif mutation == "intent":
        body["intent_id"] = "other_intent"
    elif mutation == "receipt_nonce":
        body["operator_nonce"] = "b"*32
    elif mutation == "rotation":
        body["rotation_sha256"] = "c"*64
    elif mutation == "event_digest":
        body["journal_event_sha256"] = "f"*64
    elif mutation == "head":
        body["witness_head_sha256"] = lab["heads"][0]
    elif mutation == "sequence":
        body["witness_sequence"] = 3
    elif mutation == "old_epoch":
        body["old_epoch"] = 6
        body["new_epoch"] = 7
    elif mutation == "new_epoch":
        body["old_epoch"] = 3
        body["new_epoch"] = 4
    elif mutation == "expired":
        body["verified_unix"] = NOW-100
        body["expires_unix"] = NOW-1
    elif mutation == "before_valid":
        body["verified_unix"] = NOW+1
        body["expires_unix"] = NOW+61
    elif mutation == "witness_rollback":
        overrides["witness_envelopes"] = lab["wires"][:1]
    elif mutation in ("witness_sig", "wrong_witness_nonce"):
        forged = list(lab["wires"][:2])
        w = json.loads(forged[-1])
        if mutation == "witness_sig":
            w["signature"] = "0"*128
        else:
            w["statement"]["consumed_operator_nonces"] = ["b"*32]
        forged[-1] = json.dumps(w).encode()
        overrides["witness_envelopes"] = forged
    signed = wire_receipt(lab["receipt_secret"], body)
    if mutation == "receipt_sig":
        obj = json.loads(signed)
        obj["signature"] = "0"*128
        signed = json.dumps(obj).encode()
    with pytest.raises(ValueError):
        inspect(lab, signed, **overrides)


def test_duplicate_nested_signed_field_rejected(lab):
    body = receipt_body(lab, final=False)
    signed = wire_receipt(lab["receipt_secret"], body)
    changed = signed.replace(
        b'"old_epoch":4', b'"old_epoch":3,"old_epoch":4'
    )
    assert changed != signed
    with pytest.raises(ValueError):
        inspect(lab, changed)


def test_witness_and_receipt_signer_must_have_different_public_keys(lab):
    body = receipt_body(lab, final=False)
    with pytest.raises(ValueError, match="distinct"):
        inspect(
            lab, wire_receipt(lab["receipt_secret"], body),
            trusted_receipt_public_key=lab["witness_pub"],
        )


def test_journal_changed_after_receipt_signature_cannot_match(lab):
    body = receipt_body(lab, final=False)
    signed = wire_receipt(lab["receipt_secret"], body)
    # Advancing the journal makes an old correctly signed event obsolete.
    record_candidate_milestone(
        lab["journal"], intent_id=INTENT, next_stage=STAGES[3],
    )
    with pytest.raises(ValueError, match="journal"):
        inspect(lab, signed)


def test_receipt_for_unwitnessed_sqlite_stage_cannot_be_signed(lab):
    body = receipt_body(lab, final=False)
    body["stage"] = "operator_db_recorded"
    with pytest.raises(ValueError):
        canonical_milestone_receipt(body)


def test_final_receipt_requires_correct_genesis_retirement(lab):
    body = receipt_body(lab, final=True)
    forged = list(lab["wires"])
    item = json.loads(forged[0])
    item["statement"]["verifier_epoch"] = 5
    forged[0] = json.dumps(item).encode()
    with pytest.raises(ValueError):
        inspect(lab, wire_receipt(lab["receipt_secret"], body),
                final=True, witness_envelopes=forged)


def test_two_signature_checks_still_not_proof_of_external_process_provenance(lab):
    body = receipt_body(lab, final=False)
    signed = wire_receipt(lab["receipt_secret"], body)
    result = inspect(lab, signed)
    # This private key lives in the same test process. An operator would need
    # hardware-/OS-protected key custody and independent execution tracing.
    assert result.receipt_signer_independent_execution_proven is False
    assert result.real_external_write_observed is False
    assert result.authorizes_mutation is False


def test_module_cannot_sign_open_databases_or_promote():
    import core.selfdev_signed_witness_milestone as module
    text = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager", "os.replace(",
        "INSERT INTO", "UPDATE ", "DELETE FROM",
    ):
        assert forbidden not in text
    assert "production_deployment_authorized: bool = False" in text
    assert "real_external_write_observed: bool = False" in text
    assert "automatic_recovery_permitted: bool = False" in text
