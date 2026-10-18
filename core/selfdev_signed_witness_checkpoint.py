"""Read-only validation of independently signed key/nonce witness checkpoints.

CRITICAL: Signing keys, actual witness storage, protected/latest head anchor,
operator authentication and crash-safe inter-service commit are NOT provided.
A valid old signed history is replayable if its independently pinned latest
digest is stale. Never authorize production mutation based on this module.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.selfdev_operator_signed_review import DEVICE
from core.selfdev_verifier_key_rotation import key_fingerprint

DOMAIN = b"MyAI/external-key-state-witness/checkpoint/v1\0"
ISSUER = "myai-external-checkpoint-witness-v1"
AUDIENCE = "myai-offline-updater-inspection-only"
PURPOSE = "read-only-monotonic-state-evidence"
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX128 = re.compile(r"[0-9a-f]{128}\Z")
MAX_WIRE = 30000
MAX_CHAIN = 32
MAX_MEMBERS = 256
_FIELDS = frozenset({
    "version", "issuer", "audience", "purpose", "device_id",
    "sequence", "verifier_epoch", "verifier_public_key_hex",
    "verifier_fingerprint", "retired_verifier_fingerprints",
    "consumed_operator_nonces", "previous_checkpoint_sha256", "recorded_unix",
})


@dataclass(frozen=True)
class WitnessSnapshot:
    device_id: str
    sequence: int
    verifier_epoch: int
    verifier_public_key: bytes
    verifier_fingerprint: str
    retired_verifier_fingerprints: frozenset[str]
    consumed_operator_nonces: frozenset[str]
    checkpoint_sha256: str
    signature_verified: bool = True
    independently_pinned_head_matched: bool = True
    actual_external_witness_storage_verified: bool = False
    witness_signing_key_provisioned: bool = False
    power_loss_or_restore_resistance_verified: bool = False
    external_head_advancement_performed: bool = False
    human_approval_verified: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _unique_object(pairs):
    obj = {}
    for k, v in pairs:
        if k in obj:
            raise ValueError("Duplicate witness JSON member")
        obj[k] = v
    return obj


def _reject_nonfinite(_):
    raise ValueError("Nonfinite witness number")


def _hex(value, pattern, label):
    if type(value) is not str or pattern.fullmatch(value) is None:
        raise ValueError("Invalid " + label)
    return value


def _members(values, pattern, label):
    if (type(values) is not list or len(values) > MAX_MEMBERS
            or any(type(x) is not str or pattern.fullmatch(x) is None
                   for x in values)
            or values != sorted(set(values))):
        raise ValueError("Unsorted, duplicate or malformed " + label)
    return frozenset(values)


def canonical_witness_checkpoint(statement):
    if type(statement) is not dict or set(statement) != _FIELDS:
        raise ValueError("Unexpected witness checkpoint fields")
    if type(statement["version"]) is not int or statement["version"] != 1:
        raise ValueError("Unsupported witness checkpoint version")
    if (statement["issuer"] != ISSUER or statement["purpose"] != PURPOSE
            or statement["audience"] != AUDIENCE):
        raise ValueError("Wrong witness signature domain")
    device = statement["device_id"]
    if type(device) is not str or DEVICE.fullmatch(device) is None:
        raise ValueError("Malformed witness device identity")
    seq, epoch, recorded = (
        statement["sequence"], statement["verifier_epoch"],
        statement["recorded_unix"],
    )
    if (type(seq) is not int or not 1 <= seq < 2**31
            or type(epoch) is not int or not 1 <= epoch < 2**31
            or type(recorded) is not int or recorded < 0):
        raise ValueError("Invalid witness sequence, epoch or time")
    public_hex = _hex(
        statement["verifier_public_key_hex"], HEX64,
        "verifier public key",
    )
    fingerprint = _hex(
        statement["verifier_fingerprint"], HEX64, "verifier fingerprint",
    )
    if key_fingerprint(bytes.fromhex(public_hex)) != fingerprint:
        raise ValueError("Witness verifier key fingerprint mismatch")
    retired = _members(
        statement["retired_verifier_fingerprints"], HEX64,
        "retired verifier keys",
    )
    consumed = _members(
        statement["consumed_operator_nonces"], HEX32,
        "consumed operator challenges",
    )
    if fingerprint in retired:
        raise ValueError("Active verifier key is retired")
    _hex(
        statement["previous_checkpoint_sha256"], HEX64,
        "previous witness checkpoint",
    )
    return DOMAIN + json.dumps(
        statement, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def _parse_signed(wire, witness_public_key):
    if type(wire) is not bytes or not 0 < len(wire) <= MAX_WIRE:
        raise ValueError("Oversized or malformed witness envelope")
    try:
        obj = json.loads(
            wire.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_nonfinite,
        )
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("Invalid witness envelope JSON") from exc
    if type(obj) is not dict or set(obj) != {"statement", "signature"}:
        raise ValueError("Unsupported witness envelope layout")
    statement = obj["statement"]
    signed = canonical_witness_checkpoint(statement)
    signature = _hex(obj["signature"], HEX128, "witness signature")
    try:
        Ed25519PublicKey.from_public_bytes(witness_public_key).verify(
            bytes.fromhex(signature), signed,
        )
    except (ValueError, InvalidSignature) as exc:
        raise ValueError("Invalid independently pinned witness signature") from exc
    return statement, hashlib.sha256(signed).hexdigest()


def inspect_witness_chain(
    envelopes, *, trusted_witness_public_key,
    independently_pinned_genesis_sha256,
    independently_pinned_latest_sha256, expected_device_id,
):
    """Verify finite append-only chain against two OUT-OF-BAND trusted hashes.

    A compromised caller able to select either trusted hash can replay an old
    valid signed history; no stored head, signing service or anti-rollback
    hardware is created by this pure function.
    """
    witness_fingerprint = key_fingerprint(trusted_witness_public_key)
    _hex(independently_pinned_genesis_sha256, HEX64, "pinned genesis digest")
    _hex(independently_pinned_latest_sha256, HEX64, "pinned latest digest")
    if (type(expected_device_id) is not str
            or DEVICE.fullmatch(expected_device_id) is None):
        raise ValueError("Invalid trusted device id")
    if (type(envelopes) not in (tuple, list)
            or not 1 <= len(envelopes) <= MAX_CHAIN):
        raise ValueError("Invalid bounded witness checkpoint chain")
    previous = None
    for index, wire in enumerate(envelopes):
        statement, digest = _parse_signed(wire, trusted_witness_public_key)
        if statement["device_id"] != expected_device_id:
            raise ValueError("Witness checkpoint belongs to different device")
        if index == 0:
            if (statement["sequence"] != 1
                    or statement["previous_checkpoint_sha256"] != "0" * 64
                    or digest != independently_pinned_genesis_sha256):
                raise ValueError("Untrusted first witness checkpoint")
        else:
            assert previous is not None
            old, old_digest = previous
            if (statement["sequence"] != old["sequence"] + 1
                    or statement["previous_checkpoint_sha256"] != old_digest
                    or statement["recorded_unix"] < old["recorded_unix"]):
                raise ValueError("Witness checkpoint chain diverged")
            prior_retired = set(old["retired_verifier_fingerprints"])
            new_retired = set(statement["retired_verifier_fingerprints"])
            prior_consumed = set(old["consumed_operator_nonces"])
            current_consumed = set(statement["consumed_operator_nonces"])
            if (not prior_consumed.issubset(current_consumed)
                    or not prior_retired.issubset(new_retired)):
                raise ValueError("Witness history lost prior revocations or nonces")
            if statement["verifier_epoch"] == old["verifier_epoch"]:
                if (statement["verifier_public_key_hex"] != old["verifier_public_key_hex"]
                        or new_retired != prior_retired
                        or current_consumed == prior_consumed):
                    raise ValueError("Unjustified witness sequence update")
            elif statement["verifier_epoch"] == old["verifier_epoch"] + 1:
                if (statement["verifier_fingerprint"] ==
                        old["verifier_fingerprint"]
                        or new_retired != prior_retired | {
                            old["verifier_fingerprint"]
                        }):
                    raise ValueError("Key change did not retire exactly old key")
            else:
                raise ValueError("Witness verifier epoch rolled back or skipped")
        previous = statement, digest
    assert previous is not None
    final, latest_digest = previous
    if latest_digest != independently_pinned_latest_sha256:
        raise ValueError("Witness head differs from separately pinned latest digest")
    return WitnessSnapshot(
        device_id=expected_device_id,
        sequence=final["sequence"],
        verifier_epoch=final["verifier_epoch"],
        verifier_public_key=bytes.fromhex(final["verifier_public_key_hex"]),
        verifier_fingerprint=final["verifier_fingerprint"],
        retired_verifier_fingerprints=frozenset(
            final["retired_verifier_fingerprints"]
        ),
        consumed_operator_nonces=frozenset(
            final["consumed_operator_nonces"]
        ),
        checkpoint_sha256=latest_digest,
    )
