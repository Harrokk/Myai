"""Adversarial Ed25519 fake-key-only operator review tests, never device I/O."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_operator_signed_review import (
    AUDIENCE, DOMAIN, ISSUER, PURPOSE, OperatorReview,
    canonical_operator_review, inspect_operator_review,
)
from core.selfdev_verifier_key_rotation import (
    TrustedVerifierKey, canonical_rotation, key_fingerprint,
    ISSUER as VERIFIER_ISSUER, PURPOSE as VERIFIER_PURPOSE,
    AUDIENCE as VERIFIER_AUDIENCE,
)

NOW = 1_800_000_000
DEVICE = "myai-ventuno-test-unit"
NONCE = "d" * 32


def keypair():
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def proposal(old_pub, new_pub, **patches):
    result = {
        "version": 1,
        "issuer": VERIFIER_ISSUER, "purpose": VERIFIER_PURPOSE,
        "audience": VERIFIER_AUDIENCE,
        "old_epoch": 4, "new_epoch": 5,
        "old_key_sha256": key_fingerprint(old_pub),
        "new_key_hex": new_pub.hex(),
        "new_key_sha256": key_fingerprint(new_pub),
        "operator_nonce": NONCE,
        "not_before_unix": NOW - 20, "expires_unix": NOW + 70,
    }
    result.update(patches)
    return result


def signed_fixture():
    old_secret, old_pub = keypair()
    new_secret, new_pub = keypair()
    operator_secret, operator_pub = keypair()
    rotated = proposal(old_pub, new_pub)
    bytes_to_sign = canonical_rotation(rotated)
    rotation = json.dumps({
        "statement": rotated,
        "previous_signature": old_secret.sign(bytes_to_sign).hex(),
        "proposed_signature": new_secret.sign(bytes_to_sign).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    review = {
        "version": 1,
        "issuer": ISSUER, "purpose": PURPOSE, "audience": AUDIENCE,
        "device_id": DEVICE,
        "rotation_sha256": hashlib.sha256(bytes_to_sign).hexdigest(),
        "old_key_sha256": key_fingerprint(old_pub),
        "new_key_sha256": key_fingerprint(new_pub),
        "old_epoch": 4, "new_epoch": 5,
        "operator_challenge": NONCE,
        "not_before_unix": NOW - 10, "expires_unix": NOW + 60,
    }
    return (old_secret, new_secret, operator_secret, operator_pub,
            TrustedVerifierKey(old_pub, 4), new_pub, rotation, review)


def sign_review(private, statement):
    data = canonical_operator_review(statement)
    return json.dumps({
        "statement": statement,
        "signature": private.sign(data).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()


def inspect(envelope, rotation, operator_public, anchor, **kwargs):
    params = {
        "trusted_operator_public_key": operator_public,
        "trusted_verifier_anchor": anchor,
        "expected_device_id": DEVICE,
        "expected_operator_challenge": NONCE,
        "now_unix": NOW,
    }
    params.update(kwargs)
    return inspect_operator_review(envelope, rotation, **params)


def test_three_distinct_test_keys_give_inspection_only_result():
    _, _, operator, operator_pub, anchor, new_pub, rotation, statement = signed_fixture()
    result = inspect(sign_review(operator, statement), rotation, operator_pub, anchor)
    assert isinstance(result, OperatorReview)
    assert result.device_id == DEVICE
    assert result.old_epoch == 4 and result.proposed_epoch == 5
    assert result.old_key_sha256 == key_fingerprint(anchor.public_key)
    assert result.proposed_key_sha256 == key_fingerprint(new_pub)
    assert result.pinned_operator_signature_verified is True
    assert result.verifier_dual_signature_verified is True
    assert result.independently_authenticated_human_intent_verified is False
    assert result.durable_operator_nonce_consumption_verified is False
    assert result.independent_checkpoint_advanced is False
    assert result.verifier_signing_key_activated is False
    assert result.authorizes_mutation is False
    assert result.production_deployment_authorized is False
    with pytest.raises(FrozenInstanceError):
        result.verifier_signing_key_activated = True


def test_order_independent_canonical_review_with_domain_separation():
    *_, statement = signed_fixture()
    canonical = canonical_operator_review(statement)
    assert canonical.startswith(DOMAIN)
    assert canonical_operator_review(
        dict(reversed(list(statement.items())))
    ) == canonical


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 2},
    {"issuer": "myai-runtime"}, {"purpose": "promote"},
    {"audience": "systemd-verifier"}, {"device_id": "../prod"},
    {"device_id": ""}, {"device_id": "x" * 65},
    {"rotation_sha256": "A" * 64},
    {"new_key_sha256": "0" * 63}, {"old_key_sha256": 0},
    {"old_epoch": True}, {"old_epoch": -1}, {"new_epoch": 4},
    {"new_epoch": 6}, {"old_epoch": 4.0},
    {"operator_challenge": "D" * 32},
    {"not_before_unix": True}, {"expires_unix": 0},
    {"expires_unix": NOW + 400},
    {"not_before_unix": NOW + 100},
])
def test_invalid_proposed_operator_review_refused(patch):
    *_, statement = signed_fixture()
    statement.update(patch)
    with pytest.raises(ValueError):
        canonical_operator_review(statement)


@pytest.mark.parametrize("field", [
    "operator_public_key", "new_anchor", "private_key", "approval", "human_verified",
    "shell_command", "target_path", "production_authorized", "nonce_ledger",
])
def test_untrusted_extra_claims_rejected(field):
    *_, statement = signed_fixture()
    statement[field] = True
    with pytest.raises(ValueError):
        canonical_operator_review(statement)


@pytest.mark.parametrize("changed", [
    "other_device", "other_nonce", "wrong_operator", "wrong_verifier",
    "wrong_epoch", "edited_signature", "wrong_digest", "wrong_new_key",
    "tampered_device", "tampered_old_fingerprint", "tampered_new_fingerprint",
    "tampered_epoch", "tampered_nonce",
])
def test_any_cross_domain_claim_or_signer_mismatch_fails(changed):
    _, _, operator, operator_pub, anchor, new_pub, rotation, statement = signed_fixture()
    overrides = {}
    if changed == "other_device":
        overrides["expected_device_id"] = "some-other-board"
    if changed == "other_nonce":
        overrides["expected_operator_challenge"] = "e" * 32
    if changed == "wrong_operator":
        operator_pub = keypair()[1]
    if changed == "wrong_verifier":
        anchor = TrustedVerifierKey(keypair()[1], 4)
    if changed == "wrong_epoch":
        anchor = TrustedVerifierKey(anchor.public_key, 3)
    if changed == "wrong_digest":
        statement["rotation_sha256"] = "a" * 64
    if changed == "wrong_new_key":
        statement["new_key_sha256"] = "f" * 64
    envelope = sign_review(operator, statement)
    wrapped = json.loads(envelope)
    if changed == "edited_signature":
        wrapped["signature"] = "1" * 128
    if changed == "tampered_device":
        wrapped["statement"]["device_id"] = "other-device"
    if changed == "tampered_old_fingerprint":
        wrapped["statement"]["old_key_sha256"] = "b" * 64
    if changed == "tampered_new_fingerprint":
        wrapped["statement"]["new_key_sha256"] = "f" * 64
    if changed == "tampered_epoch":
        wrapped["statement"]["old_epoch"] = 3
    if changed == "tampered_nonce":
        wrapped["statement"]["operator_challenge"] = "f" * 32
    with pytest.raises(ValueError):
        inspect(json.dumps(wrapped).encode(), rotation, operator_pub, anchor, **overrides)


def test_replay_same_signature_on_another_board_refused():
    _, _, op, op_pub, anchor, _, rotation, review = signed_fixture()
    wire = sign_review(op, review)
    with pytest.raises(ValueError, match="device"):
        inspect(wire, rotation, op_pub, anchor,
                expected_device_id="different-ventuno")


@pytest.mark.parametrize("now", [
    NOW - 11, NOW + 60, NOW + 100, True, -1,
])
def test_time_validity_is_bounded_and_fail_closed(now):
    _, _, op, op_pub, anchor, _, rotation, statement = signed_fixture()
    with pytest.raises(ValueError):
        inspect(sign_review(op, statement), rotation, op_pub, anchor,
                now_unix=now)


@pytest.mark.parametrize("corrupt", [
    b"", b"\xff", b"{}", b"[]", b"not-json",
    b'{"statement":1,"signature":"0","signature":"0"}',
    b'{"statement":NaN,"signature":"0"}',
    b"x" * 3073,
])
def test_duplicate_nonfinite_bad_or_oversized_json_is_rejected(corrupt):
    _, _, _, op_pub, anchor, _, rotation, _ = signed_fixture()
    with pytest.raises(ValueError):
        inspect(corrupt, rotation, op_pub, anchor)


def test_duplicate_nested_operator_nonce_never_overrides_existing():
    _, _, op, op_pub, anchor, _, rotation, statement = signed_fixture()
    wire = sign_review(op, statement)
    tampered = wire.replace(b'"operator_challenge":"' + NONCE.encode() + b'"',
                            b'"operator_challenge":"' + NONCE.encode()
                            + b'","operator_challenge":"e' + b'e' * 31 + b'"')
    assert tampered != wire
    with pytest.raises(ValueError):
        inspect(tampered, rotation, op_pub, anchor)


def test_approval_only_signed_by_verifier_private_key_is_not_independent():
    old, _, _, _, anchor, _, rotation, statement = signed_fixture()
    op_public = keypair()[1]
    wire = sign_review(old, statement)
    with pytest.raises(ValueError):
        inspect(wire, rotation, op_public, anchor)


def test_operator_public_key_must_not_be_same_as_old_verifier():
    old, _, _, _, anchor, _, rotation, statement = signed_fixture()
    with pytest.raises(ValueError, match="separate"):
        inspect(sign_review(old, statement), rotation,
                anchor.public_key, anchor)


def test_operator_public_key_must_not_be_proposed_verifier_key():
    _, new, _, _, anchor, new_public, rotation, statement = signed_fixture()
    with pytest.raises(ValueError, match="separate"):
        inspect(sign_review(new, statement), rotation,
                new_public, anchor)


def test_review_signature_and_old_new_verifier_signatures_are_both_required():
    _, _, op, op_pub, anchor, _, rotation, statement = signed_fixture()
    original = json.loads(rotation)
    original["previous_signature"] = "0" * 128
    with pytest.raises(ValueError, match="signature"):
        inspect(sign_review(op, statement), json.dumps(original).encode(),
                op_pub, anchor)
    original = json.loads(rotation)
    original["proposed_signature"] = "0" * 128
    with pytest.raises(ValueError, match="signature"):
        inspect(sign_review(op, statement), json.dumps(original).encode(),
                op_pub, anchor)


def test_missing_separate_operator_key_or_trusted_context_rejected():
    _, _, op, op_pub, anchor, _, rotation, review = signed_fixture()
    wire = sign_review(op, review)
    for bad in (None, b"", "test", True, b"\x00" * 31):
        with pytest.raises(ValueError):
            inspect(wire, rotation, bad, anchor)
    with pytest.raises(ValueError):
        inspect(wire, rotation, op_pub, None)
    with pytest.raises(ValueError):
        inspect(wire, rotation, op_pub, anchor,
                expected_operator_challenge="Q" * 32)


def test_module_does_not_sign_or_mutate_live_trust(tmp_path):
    from core import selfdev_operator_signed_review as review
    source = Path(review.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager",
        "save_verification(", "key.sign(", "os.chown(",
    ):
        assert forbidden not in source
    assert "production_deployment_authorized: bool = False" in source
    assert "independently_authenticated_human_intent_verified: bool = False" in source
    assert "durable_operator_nonce_consumption_verified: bool = False" in source
