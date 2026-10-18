"""NON-AUTHORIZING inspection of proposed Ed25519 verifier key rotations.

No keypair generation, private key, file writes, systemd, network, promotion,
database, live trusted-key replacement or device action. Caller MUST source
its currently pinned key, revocation list, expected operator nonce and exact
independently approved transition digest from a protected OUT-OF-BAND channel.
This module cannot establish that trust channel or protect its persisted state.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.selfdev_signed_evidence import inspect_signed_evidence

DOMAIN = b"MyAI/independent-verifier/key-rotation-proposal/v1\0"
ISSUER = "myai-independent-verifier-key-management"
PURPOSE = "inspection-only-proposed-key-rotation"
AUDIENCE = "myai-updater-offline-key-review"
MAX_ENVELOPE = 4096
MAX_LIFETIME = 900
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX128 = re.compile(r"[0-9a-f]{128}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
FIELDS = frozenset({
    "version", "issuer", "purpose", "audience", "old_epoch", "new_epoch",
    "old_key_sha256", "new_key_hex", "new_key_sha256",
    "operator_nonce", "not_before_unix", "expires_unix",
})


@dataclass(frozen=True)
class TrustedVerifierKey:
    """Caller-owned anchor, NEVER accepted from an untrusted envelope."""

    public_key: bytes
    epoch: int
    revoked_fingerprints: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RotationInspection:
    old_epoch: int
    proposed_epoch: int
    old_key_sha256: str
    proposed_key_sha256: str
    approved_payload_sha256_matched: bool = True
    previous_key_signature_verified: bool = True
    proposed_key_possession_signature_verified: bool = True
    trusted_operator_approval_channel_verified: bool = False
    durable_epoch_storage_verified: bool = False
    actual_key_rotation_performed: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def key_fingerprint(public_key):
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("Pinned Ed25519 public key must be exactly 32 bytes")
    return hashlib.sha256(public_key).hexdigest()


def _validate_anchor(anchor):
    if type(anchor) is not TrustedVerifierKey:
        raise ValueError("Trusted updater-owned key anchor required")
    if type(anchor.epoch) is not int or not 1 <= anchor.epoch < 2**31:
        raise ValueError("Invalid pinned key epoch")
    current = key_fingerprint(anchor.public_key)
    revoked = anchor.revoked_fingerprints
    if (type(revoked) is not frozenset or len(revoked) > 256
            or any(type(item) is not str or HEX64.fullmatch(item) is None
                   for item in revoked)):
        raise ValueError("Malformed trusted revocation policy")
    if current in revoked:
        raise ValueError("Current pinned verifier key is revoked")
    return current


def _strict_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate signed key-rotation JSON field")
        result[key] = value
    return result


def _reject_nonfinite(_):
    raise ValueError("Nonfinite value in signed key rotation")


def _expect_hex(value, expression, label):
    if type(value) is not str or expression.fullmatch(value) is None:
        raise ValueError("Invalid " + label)
    return value


def canonical_rotation(statement):
    """Strict canonical domain-separated signing bytes for fixed schema v1."""
    if type(statement) is not dict or set(statement) != FIELDS:
        raise ValueError("Key rotation statement has unknown/missing fields")
    if type(statement["version"]) is not int or statement["version"] != 1:
        raise ValueError("Unsupported key rotation version")
    if (statement["issuer"] != ISSUER or statement["purpose"] != PURPOSE
            or statement["audience"] != AUDIENCE):
        raise ValueError("Wrong key-rotation signing domain")
    if (type(statement["old_epoch"]) is not int
            or type(statement["new_epoch"]) is not int
            or statement["old_epoch"] < 1
            or statement["new_epoch"] != statement["old_epoch"] + 1
            or statement["new_epoch"] >= 2**31):
        raise ValueError("Key rotation epochs must advance exactly once")
    _expect_hex(statement["old_key_sha256"], HEX64, "old key fingerprint")
    _expect_hex(statement["new_key_hex"], HEX64, "new Ed25519 key")
    _expect_hex(statement["new_key_sha256"], HEX64, "new key fingerprint")
    _expect_hex(statement["operator_nonce"], HEX32, "operator nonce")
    new_key = bytes.fromhex(statement["new_key_hex"])
    if key_fingerprint(new_key) != statement["new_key_sha256"]:
        raise ValueError("New verifier fingerprint is inconsistent")
    if statement["old_key_sha256"] == statement["new_key_sha256"]:
        raise ValueError("Reusing same key is not a rotation")
    start = statement["not_before_unix"]
    expiry = statement["expires_unix"]
    if (type(start) is not int or type(expiry) is not int or start < 0
            or not start < expiry or expiry - start > MAX_LIFETIME):
        raise ValueError("Invalid or excessively long key transition lifetime")
    return DOMAIN + json.dumps(
        statement, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def inspect_rotation(
    envelope, *, pinned_key, expected_operator_nonce,
    independently_approved_payload_sha256, now_unix=None,
):
    """Review a *proposed* rotation; never change which key is trusted.

    Dual Ed25519 signatures are necessary but NOT operator approval.
    An external operator must separately approve the EXACT canonical digest.
    A trusted updater must persist a monotonic epoch/denylist atomically
    before it could ever select a new pinned key. None is implemented here.
    """
    old_id = _validate_anchor(pinned_key)
    nonce = _expect_hex(expected_operator_nonce, HEX32, "trusted operator nonce")
    approval = _expect_hex(
        independently_approved_payload_sha256, HEX64,
        "independently approved transition digest",
    )
    if type(envelope) is not bytes or not 0 < len(envelope) <= MAX_ENVELOPE:
        raise ValueError("Invalid or oversized key-rotation envelope")
    now = int(time.time()) if now_unix is None else now_unix
    if type(now) is not int or now < 0:
        raise ValueError("Invalid trusted time")
    try:
        parsed = json.loads(
            envelope.decode("utf-8"),
            object_pairs_hook=_strict_object,
            parse_constant=_reject_nonfinite,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Malformed signed rotation envelope") from error
    if (type(parsed) is not dict or set(parsed) !=
            {"statement", "previous_signature", "proposed_signature"}):
        raise ValueError("Unexpected rotation envelope fields")
    proposal = parsed["statement"]
    signed = canonical_rotation(proposal)
    proposed_id = proposal["new_key_sha256"]
    if (proposal["old_epoch"] != pinned_key.epoch
            or proposal["old_key_sha256"] != old_id
            or proposal["operator_nonce"] != nonce):
        raise ValueError("Rotation does not match pinned state and operator nonce")
    if proposed_id in pinned_key.revoked_fingerprints:
        raise ValueError("Cannot reintroduce a revoked verifier key")
    if hashlib.sha256(signed).hexdigest() != approval:
        raise ValueError("Unapproved key-rotation payload")
    if not proposal["not_before_unix"] <= now < proposal["expires_unix"]:
        raise ValueError("Proposed key rotation is premature or expired")
    old_sig = _expect_hex(parsed["previous_signature"], HEX128,
                          "previous verifier signature")
    new_sig = _expect_hex(parsed["proposed_signature"], HEX128,
                          "proposed verifier signature")
    try:
        Ed25519PublicKey.from_public_bytes(pinned_key.public_key).verify(
            bytes.fromhex(old_sig), signed,
        )
        Ed25519PublicKey.from_public_bytes(
            bytes.fromhex(proposal["new_key_hex"])
        ).verify(bytes.fromhex(new_sig), signed)
    except (InvalidSignature, ValueError) as error:
        raise ValueError("Invalid old/new Ed25519 transition signature") from error
    return RotationInspection(
        old_epoch=pinned_key.epoch,
        proposed_epoch=proposal["new_epoch"],
        old_key_sha256=old_id,
        proposed_key_sha256=proposed_id,
    )


def inspect_evidence_under_pinned_key(envelope, *, pinned_key, **expected_context):
    """Preserve PR #333 inspection-only guarantees under pinned key policy.

    Revoked current key is rejected even when its evidence signature verifies.
    No automatic selection of unapproved, old, or proposed keys.
    """
    _validate_anchor(pinned_key)
    if "trusted_verifier_public_key" in expected_context:
        raise ValueError("Untrusted evidence caller cannot replace pinned key")
    return inspect_signed_evidence(
        envelope,
        trusted_verifier_public_key=pinned_key.public_key,
        **expected_context,
    )
