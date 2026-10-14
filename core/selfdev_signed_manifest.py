"""Pure, inspection-only Ed25519 manifest verification.

No files, Git, IPC, privileged updater operations, or deployment functions.
Trusted public keys must be provisioned INDEPENDENTLY of attacker input.
A valid signature attests only to the inspected manifest's key signature.
"""

import base64
from dataclasses import dataclass
import hashlib
import json
import re

from core.selfdev_request_protocol import parse_inspection_request, InspectionRequest


_MAX_ENVELOPE = 40 * 1024
_KEY_ID = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")
_CONTEXT = "myai:inspection-only:ed25519:v1"


@dataclass(frozen=True)
class SignedInspectionPreview:
    request: InspectionRequest
    signer_key_id: str
    signed_sha256: str
    signature_valid: bool = True
    requires_human_approval: bool = True
    authorizes_mutation: bool = False


def _unique_object(pairs):
    output = {}
    for key, value in pairs:
        if key in output:
            raise ValueError("Duplicate field in signed manifest.")
        output[key] = value
    return output


def _reject_constant(value):
    raise ValueError("Nonfinite value in signed manifest.")


def _canonical(obj):
    return json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        ensure_ascii=True, allow_nan=False,
    ).encode("ascii")


def signed_preview_bytes(*, key_id, payload):
    """Canonical signing bytes for offline verification and test fixtures.

    This helper does NOT sign anything and does not authenticate input.
    """
    if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
        raise ValueError("Invalid signer key ID.")
    if type(payload) is not dict:
        raise ValueError("Expected inspection manifest object.")
    return _canonical({
        "context": _CONTEXT,
        "algorithm": "Ed25519",
        "key_id": key_id,
        "payload": payload,
        "version": 1,
    })


def verify_signed_inspection_preview(
    envelope_bytes, trusted_public_keys, *, now_unix=None,
):
    """Verify a signed preview without ever granting mutation privileges.

    The caller must supply out-of-band trusted public keys. This function
    intentionally has no callback, file path, connection or updater reference.
    """
    if (
        type(envelope_bytes) is not bytes
        or not 0 < len(envelope_bytes) <= _MAX_ENVELOPE
    ):
        raise ValueError("Invalid signed manifest byte size.")
    if type(trusted_public_keys) is not dict:
        raise TypeError("Trusted keyring must be supplied out of band.")
    try:
        envelope = json.loads(
            envelope_bytes.decode("utf-8"),
            object_pairs_hook=_unique_object,
            parse_constant=_reject_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Malformed signed manifest.") from error
    if type(envelope) is not dict or set(envelope) != {
        "version", "algorithm", "key_id", "payload", "signature"
    }:
        raise ValueError("Unexpected signed manifest structure.")
    if (
        type(envelope["version"]) is not int or envelope["version"] != 1
        or envelope["algorithm"] != "Ed25519"
    ):
        raise ValueError("Unsupported signing version or algorithm.")
    key_id = envelope["key_id"]
    if type(key_id) is not str or not _KEY_ID.fullmatch(key_id):
        raise ValueError("Invalid signer key ID.")
    public_key = trusted_public_keys.get(key_id)
    if type(public_key) is not bytes or len(public_key) != 32:
        raise ValueError("No independently trusted Ed25519 key for signer.")
    signature_text = envelope["signature"]
    if type(signature_text) is not str or len(signature_text) != 88:
        raise ValueError("Invalid Ed25519 signature encoding.")
    try:
        signature = base64.b64decode(signature_text, validate=True)
    except (ValueError, base64.binascii.Error) as error:
        raise ValueError("Invalid Ed25519 signature encoding.") from error
    if (
        len(signature) != 64
        or base64.b64encode(signature).decode("ascii") != signature_text
    ):
        raise ValueError("Noncanonical Ed25519 signature encoding.")
    payload = envelope["payload"]
    # Reuse exact preview-only schema: no shells, services, approval fields
    # or unsigned deployment actions accepted.
    canonical_payload = _canonical(payload)
    preview = parse_inspection_request(canonical_payload, now_unix=now_unix)
    message = signed_preview_bytes(key_id=key_id, payload=payload)

    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import (
            Ed25519PublicKey,
        )
    except ImportError as error:
        raise RuntimeError(
            "Ed25519 backend unavailable: reject signed preview."
        ) from error

    try:
        Ed25519PublicKey.from_public_bytes(public_key).verify(signature, message)
    except (InvalidSignature, ValueError) as error:
        raise ValueError("Ed25519 signature mismatch.") from error

    return SignedInspectionPreview(
        request=preview,
        signer_key_id=key_id,
        signed_sha256=hashlib.sha256(message).hexdigest(),
    )
