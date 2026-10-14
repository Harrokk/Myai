"""Immutable-input preview signer lifecycle policy; never install or sign.

All public-key fingerprints MUST be pinned through independent trusted
configuration. Neither a submitted manifest nor an attacker-provided keyring
can self-authorize trust, key rotation or revocation.
"""

from dataclasses import dataclass
import hashlib
import re

from core.selfdev_signed_manifest import verify_signed_inspection_preview


_KEY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MAX_RECORDS = 16


@dataclass(frozen=True)
class PreviewSignerPolicy:
    key_id: str
    public_key: bytes
    valid_from_unix: int
    valid_until_unix: int
    revoked: bool = False


def active_preview_public_keys(records, *, pinned_fingerprints, now_unix):
    """Resolve a fail-closed Ed25519 *inspection* keyring at trusted time.

    The records and separately pinned SHA-256 fingerprints are trusted
    administrative inputs, NOT part of a request or signed payload.
    Revoked keys always remain revoked regardless of timestamp.
    """
    if type(now_unix) is not int or now_unix < 0:
        raise ValueError("Trusted Unix clock must be nonnegative integer.")
    if type(records) is not tuple or not 1 <= len(records) <= _MAX_RECORDS:
        raise ValueError("Invalid trusted signer records.")
    if type(pinned_fingerprints) is not dict:
        raise ValueError("Missing out-of-band trusted public key pins.")

    by_id = {}
    fingerprints = set()
    for entry in records:
        if type(entry) is not PreviewSignerPolicy:
            raise ValueError("Malformed trusted signer record.")
        if type(entry.key_id) is not str or not _KEY_ID.fullmatch(entry.key_id):
            raise ValueError("Malformed trusted signer key ID.")
        if type(entry.public_key) is not bytes or len(entry.public_key) != 32:
            raise ValueError("Malformed trusted Ed25519 public key.")
        if (
            type(entry.valid_from_unix) is not int
            or type(entry.valid_until_unix) is not int
            or entry.valid_from_unix < 0
            or entry.valid_until_unix <= entry.valid_from_unix
            or type(entry.revoked) is not bool
        ):
            raise ValueError("Malformed trusted signer lifecycle window.")
        if entry.key_id in by_id:
            raise ValueError("Duplicate trusted signer key ID.")
        fingerprint = hashlib.sha256(entry.public_key).hexdigest()
        if fingerprint in fingerprints:
            raise ValueError("Public key reused across distinct signer identities.")
        fingerprints.add(fingerprint)
        by_id[entry.key_id] = (entry, fingerprint)

    if set(pinned_fingerprints) != set(by_id):
        raise ValueError("Trusted signer policy differs from pinned identities.")
    for key_id, (_, fingerprint) in by_id.items():
        pinned = pinned_fingerprints[key_id]
        if (
            type(pinned) is not str
            or not _SHA256.fullmatch(pinned)
            or pinned != fingerprint
        ):
            raise ValueError("Independent trusted public key fingerprint mismatch.")

    active = {
        key_id: record.public_key
        for key_id, (record, _) in by_id.items()
        if not record.revoked
        and record.valid_from_unix <= now_unix < record.valid_until_unix
    }
    if not active:
        raise ValueError("No currently active and nonrevoked preview signers.")
    return active


def verify_preview_with_signer_policy(
    envelope_bytes, records, *, pinned_fingerprints, now_unix,
):
    """Verify using only currently trusted keys; cannot authorize mutation."""
    keys = active_preview_public_keys(
        records,
        pinned_fingerprints=pinned_fingerprints,
        now_unix=now_unix,
    )
    return verify_signed_inspection_preview(
        envelope_bytes, keys, now_unix=now_unix
    )
