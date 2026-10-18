"""Adversarial fake-key-only tests for inspection-only verifier rotation policy."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_verifier_key_rotation import (
    AUDIENCE, DOMAIN, ISSUER, PURPOSE,
    RotationInspection, TrustedVerifierKey,
    canonical_rotation, inspect_evidence_under_pinned_key, inspect_rotation,
    key_fingerprint,
)
from core.selfdev_signed_evidence import canonical_statement_bytes

NOW = 1_800_000_000
NONCE = "a" * 32


def keys():
    private = Ed25519PrivateKey.generate()  # Only in test; never on VENTUNO
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def sample(**patch):
    _, old = keys()
    _, new = keys()
    body = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "old_epoch": 4, "new_epoch": 5,
        "old_key_sha256": key_fingerprint(old),
        "new_key_hex": new.hex(), "new_key_sha256": key_fingerprint(new),
        "operator_nonce": NONCE,
        "not_before_unix": NOW - 10, "expires_unix": NOW + 60,
    }
    body.update(patch)
    return body


def fixture(**patch):
    old_secret, old_pub = keys()
    new_secret, new_pub = keys()
    body = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "old_epoch": 4, "new_epoch": 5,
        "old_key_sha256": key_fingerprint(old_pub),
        "new_key_hex": new_pub.hex(),
        "new_key_sha256": key_fingerprint(new_pub),
        "operator_nonce": NONCE,
        "not_before_unix": NOW - 10,
        "expires_unix": NOW + 60,
    }
    body.update(patch)
    return old_secret, new_secret, TrustedVerifierKey(old_pub, 4), body


def sign_rotation(old_secret, new_secret, body):
    canonical = canonical_rotation(body)
    wire = json.dumps({
        "statement": body,
        "previous_signature": old_secret.sign(canonical).hex(),
        "proposed_signature": new_secret.sign(canonical).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return wire, hashlib.sha256(canonical).hexdigest()


def inspect(wire, approved_digest, anchor, **kwargs):
    values = dict(
        pinned_key=anchor, expected_operator_nonce=NONCE,
        independently_approved_payload_sha256=approved_digest, now_unix=NOW,
    )
    values.update(kwargs)
    return inspect_rotation(wire, **values)


def test_complete_dual_signed_proposal_is_always_non_authorizing():
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    result = inspect(wire, digest, anchor)
    assert isinstance(result, RotationInspection)
    assert result.old_epoch == 4
    assert result.proposed_epoch == 5
    assert result.proposed_key_sha256 == body["new_key_sha256"]
    assert result.old_key_sha256 == body["old_key_sha256"]
    assert result.previous_key_signature_verified is True
    assert result.proposed_key_possession_signature_verified is True
    assert result.approved_payload_sha256_matched is True
    assert result.trusted_operator_approval_channel_verified is False
    assert result.durable_epoch_storage_verified is False
    assert result.actual_key_rotation_performed is False
    assert result.authorizes_mutation is False
    assert result.production_deployment_authorized is False
    assert anchor.public_key != bytes.fromhex(body["new_key_hex"])
    with pytest.raises(FrozenInstanceError):
        result.actual_key_rotation_performed = True


def test_canonical_order_does_not_change_signed_payload():
    _, _, _, body = fixture()
    shuffled = dict(reversed(list(body.items())))
    assert canonical_rotation(shuffled) == canonical_rotation(body)
    assert canonical_rotation(body).startswith(DOMAIN)


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 0},
    {"issuer": "selfdev-runtime"}, {"purpose": "production-promotion"},
    {"audience": "myai-runtime"}, {"old_epoch": True},
    {"old_epoch": 0}, {"old_epoch": 4.0},
    {"new_epoch": 4}, {"new_epoch": 6}, {"new_epoch": 2**31},
    {"old_key_sha256": "ABC" * 21 + "A"},
    {"operator_nonce": "Z" * 32}, {"operator_nonce": "abc"},
    {"new_key_hex": "x" * 64}, {"new_key_hex": ""},
    {"new_key_sha256": "f" * 64},
    {"not_before_unix": True}, {"expires_unix": NOW - 100},
    {"not_before_unix": NOW + 70},
    {"expires_unix": NOW + 1000},
    {"expires_unix": NOW - 10},
])
def test_invalid_rotation_claims_never_signable(patch):
    body = sample(**patch)
    with pytest.raises(ValueError):
        canonical_rotation(body)


@pytest.mark.parametrize("extra", [
    "signer_private_key", "approved", "verified_passed", "new_epoch_override",
    "target_file", "command", "auto_promote", "allow_unsigned",
])
def test_unrecognized_fields_never_accepted(extra):
    body = sample(**{extra: True})
    with pytest.raises(ValueError):
        canonical_rotation(body)


@pytest.mark.parametrize("tamper", [
    "previous_signature", "proposed_signature", "approved_digest",
    "operator_nonce", "old_fingerprint", "previous_epoch", "new_fingerprint",
])
def test_wrong_old_or_new_signature_or_context_rejected(tamper):
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    doc = json.loads(wire)
    options = {}
    if tamper == "previous_signature":
        doc["previous_signature"] = "0" * 128
    if tamper == "proposed_signature":
        doc["proposed_signature"] = "1" * 128
    if tamper == "approved_digest":
        digest = "f" * 64
    if tamper == "operator_nonce":
        options["expected_operator_nonce"] = "b" * 32
    if tamper == "old_fingerprint":
        anchor = TrustedVerifierKey(keys()[1], 4)
    if tamper == "previous_epoch":
        anchor = TrustedVerifierKey(anchor.public_key, 3)
    if tamper == "new_fingerprint":
        doc["statement"]["new_key_sha256"] = "0" * 64
    with pytest.raises(ValueError):
        inspect(json.dumps(doc).encode(), digest, anchor, **options)


def test_private_key_possession_of_old_only_cannot_install_new_key():
    old, _, anchor, body = fixture()
    other_secret, _ = keys()
    wire, digest = sign_rotation(old, other_secret, body)
    with pytest.raises(ValueError, match="signature"):
        inspect(wire, digest, anchor)


def test_private_key_possession_of_new_only_cannot_replace_old_anchor():
    _, new, anchor, body = fixture()
    other_secret, _ = keys()
    wire, digest = sign_rotation(other_secret, new, body)
    with pytest.raises(ValueError, match="signature"):
        inspect(wire, digest, anchor)


def test_signed_rotation_without_independent_operator_digest_is_blocked():
    old, new, anchor, body = fixture()
    wire, _ = sign_rotation(old, new, body)
    with pytest.raises(ValueError):
        inspect(wire, None, anchor)


@pytest.mark.parametrize("now", [NOW - 11, NOW + 60, NOW + 200, True, -1])
def test_bounded_operator_approved_transition_lifetime(now):
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    with pytest.raises(ValueError):
        inspect(wire, digest, anchor, now_unix=now)


def test_untrusted_revocation_policy_does_not_select_a_different_key():
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    anchor_revoked = TrustedVerifierKey(anchor.public_key, 4,
                                        frozenset({key_fingerprint(anchor.public_key)}))
    with pytest.raises(ValueError, match="revoked"):
        inspect(wire, digest, anchor_revoked)
    anchor_new_revoked = TrustedVerifierKey(
        anchor.public_key, 4, frozenset({body["new_key_sha256"]})
    )
    with pytest.raises(ValueError, match="revoked"):
        inspect(wire, digest, anchor_new_revoked)


@pytest.mark.parametrize("revocations", [
    set(), frozenset({"Z" * 64}), frozenset({123}),
    ["a" * 64],
])
def test_invalid_trusted_revocation_state_blocks_inspection(revocations):
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    with pytest.raises(ValueError):
        inspect(wire, digest, TrustedVerifierKey(
            anchor.public_key, 4, revocations
        ))


@pytest.mark.parametrize("bad", [
    b"", b"\xff", b"{}", b"[]", b"not json",
    b'{"statement":1,"previous_signature":"0","proposed_signature":"0","extra":true}',
    b'{"statement":NaN,"previous_signature":"0","proposed_signature":"0"}',
    b'{"statement":1,"statement":1,"previous_signature":"0","proposed_signature":"0"}',
    b"x" * 4097,
])
def test_bad_or_ambiguous_signed_envelopes_blocked(bad):
    _, _, anchor, _ = fixture()
    with pytest.raises(ValueError):
        inspect(bad, "f" * 64, anchor)


def test_duplicate_nested_json_field_rejected_even_when_signed():
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    modified = wire.replace(b'"new_epoch":5', b'"new_epoch":4,"new_epoch":5')
    assert modified != wire
    with pytest.raises(ValueError, match="Malformed"):
        inspect(modified, digest, anchor)


def test_unauthorized_envelope_cannot_supply_its_own_new_trust_anchor():
    old, new, anchor, body = fixture()
    wire, digest = sign_rotation(old, new, body)
    data = json.loads(wire)
    data["pinned_key"] = body["new_key_hex"]
    with pytest.raises(ValueError):
        inspect(json.dumps(data).encode(), digest, anchor)


def test_duplicate_reuse_of_old_key_and_skipped_epoch_are_blocked():
    old, new, anchor, body = fixture()
    body["new_key_hex"] = anchor.public_key.hex()
    body["new_key_sha256"] = key_fingerprint(anchor.public_key)
    with pytest.raises(ValueError):
        canonical_rotation(body)
    body["new_epoch"] = 7
    with pytest.raises(ValueError):
        canonical_rotation(body)


def test_pinned_key_evidence_cannot_be_overridden_by_untrusted_caller():
    _, _, anchor, _ = fixture()
    with pytest.raises(ValueError, match="replace"):
        inspect_evidence_under_pinned_key(
            b"{}", pinned_key=anchor,
            trusted_verifier_public_key=keys()[1],
        )


def test_normal_evidence_under_pinned_key_keeps_explicit_no_go():
    old, _, anchor, _ = fixture()
    statement = {
        "version": 1, "purpose": "sandbox-verification-only",
        "issuer": "myai-independent-verifier-v1",
        "audience": "myai-updater-inspection-only",
        "session_id": "session_1",
        "manifest_sha256": "a" * 64, "test_plan_sha256": "b" * 64,
        "evidence_sha256": "c" * 64, "challenge": "d" * 32,
        "verified_unix": NOW - 5, "expires_unix": NOW + 60,
        "passed": True, "sandbox": "bubblewrap",
        "network_isolated": True, "host_devices_exposed": False,
    }
    wire = json.dumps({
        "statement": statement,
        "signature": old.sign(canonical_statement_bytes(statement)).hex(),
    }).encode()
    kwargs = dict(
        expected_session_id="session_1", expected_manifest_sha256="a" * 64,
        expected_test_plan_sha256="b" * 64,
        expected_evidence_sha256="c" * 64, expected_challenge="d" * 32,
        now_unix=NOW,
    )
    outcome = inspect_evidence_under_pinned_key(
        wire, pinned_key=anchor, **kwargs,
    )
    assert outcome.signature_verified is True
    assert outcome.authorizes_mutation is False
    assert outcome.production_deployment_authorized is False
    with pytest.raises(ValueError, match="revoked"):
        inspect_evidence_under_pinned_key(
            wire, pinned_key=TrustedVerifierKey(
                anchor.public_key, 4,
                frozenset({key_fingerprint(anchor.public_key)}),
            ), **kwargs,
        )


def test_frozen_source_module_cannot_manage_keys_deploy_or_sign():
    import core.selfdev_verifier_key_rotation as rotation
    source = Path(rotation.__file__).read_text(encoding="utf-8")
    assert "Ed25519PrivateKey" not in source
    assert "sqlite3.connect" not in source
    assert "subprocess." not in source
    assert "systemctl" not in source
    assert "SelfDevPromotionManager" not in source
    assert "save_verification(" not in source
    assert "production_deployment_authorized: bool = False" in source
