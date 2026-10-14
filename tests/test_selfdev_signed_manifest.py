"""Inspection-only signed manifest tests; real Ed25519 on host with crypto."""

import base64
import hashlib
import json

import pytest

from core.selfdev_signed_manifest import (
    signed_preview_bytes, verify_signed_inspection_preview,
)

NOW = 1800000000


def payload(**overrides):
    data = {
        "version": 1,
        "action": "inspect_candidate",
        "request_id": "a" * 32,
        "revision": "b" * 40,
        "expires_unix": NOW + 60,
        "files": [{
            "path": "core/example.py",
            "sha256": hashlib.sha256(b"DATA").hexdigest(),
        }],
    }
    data.update(overrides)
    return data


def encoded_manifest(signature=None, key="signer-01", inspection=None, **kwargs):
    body = {
        "version": 1, "algorithm": "Ed25519",
        "key_id": key,
        "payload": payload() if inspection is None else inspection,
        "signature": base64.b64encode(b"\x00" * 64).decode("ascii")
        if signature is None else signature,
    }
    body.update(kwargs)
    return json.dumps(body, separators=(",", ":")).encode("utf-8")


def verify(raw, keys=None):
    if keys is None:
        keys = {"signer-01": b"\x01" * 32}
    return verify_signed_inspection_preview(raw, keys, now_unix=NOW)


@pytest.mark.parametrize("bad", [
    b"", b"{}", b"null", b"[]", b"{", b"\xff", b"x" * (40 * 1024 + 1),
    b'{"version":1,"version":1}', b'{"x":NaN}', b'{"x":Infinity}',
])
def test_invalid_envelope_is_rejected_before_signature(bad):
    with pytest.raises(ValueError):
        verify(bad)


@pytest.mark.parametrize("fields", [
    {"action": "promote"}, {"action": "rollback"},
    {"approval": "yes"}, {"script": "print('run')"},
])
def test_signed_preview_cannot_request_privileged_actions(fields):
    with pytest.raises(ValueError):
        verify(encoded_manifest(inspection=payload(**fields)))


@pytest.mark.parametrize("extra", [
    {"command": "deploy"}, {"service": "geniex"}, {"approved": True},
    {"root": "/etc"}, {"signing_key": "fake"}, {"policy": "allow"},
])
def test_extra_envelope_fields_do_not_expand_authority(extra):
    with pytest.raises(ValueError):
        verify(encoded_manifest(**extra))


@pytest.mark.parametrize("algorithm", [
    "none", "HS256", "RSA", "Ed25519;install", "", None,
])
def test_algorithm_confusion_is_denied(algorithm):
    with pytest.raises(ValueError):
        verify(encoded_manifest(algorithm=algorithm))


def test_unknown_signer_is_rejected_even_with_valid_shape():
    with pytest.raises(ValueError, match="independently trusted"):
        verify(encoded_manifest(key="other-key"))


def test_base64_signature_must_be_canonical_exact_length():
    with pytest.raises(ValueError, match="signature"):
        verify(encoded_manifest(signature="%%%"))
    with pytest.raises(ValueError, match="signature"):
        verify(encoded_manifest(signature=base64.b64encode(b"a" * 63).decode("ascii")))


def test_wrong_public_key_length_denies_before_crypto():
    with pytest.raises(ValueError, match="trusted"):
        verify(encoded_manifest(), {"signer-01": b"bad"})


def test_expired_signed_request_is_never_accepted():
    with pytest.raises(ValueError, match="Expired"):
        verify(encoded_manifest(inspection=payload(expires_unix=NOW)))


def test_signing_context_is_deterministic_but_not_approval():
    a = signed_preview_bytes(key_id="signer-01", payload=payload())
    b = signed_preview_bytes(key_id="signer-01", payload=payload())
    assert a == b and b"inspection-only" in a
    assert a != signed_preview_bytes(key_id="signer-02", payload=payload())


def test_real_ed25519_signature_roundtrip_and_tamper_checks():
    crypto = pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    private = Ed25519PrivateKey.generate()  # Ephemeral in-memory fixture only.
    public_bytes = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    manifest = payload()
    message = signed_preview_bytes(key_id="signer-01", payload=manifest)
    sig = base64.b64encode(private.sign(message)).decode("ascii")
    signed = encoded_manifest(signature=sig, inspection=manifest)
    result = verify(signed, {"signer-01": public_bytes})
    assert result.signature_valid is True
    assert result.authorizes_mutation is False
    assert result.requires_human_approval is True
    assert result.request.action == "inspect_candidate"

    tampered = payload(revision="c" * 40)
    with pytest.raises(ValueError, match="signature mismatch"):
        verify(encoded_manifest(signature=sig, inspection=tampered), {
            "signer-01": public_bytes,
        })

    second = Ed25519PrivateKey.generate()
    wrong_key = second.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    with pytest.raises(ValueError, match="signature mismatch"):
        verify(signed, {"signer-01": wrong_key})

    with pytest.raises(ValueError, match="signature mismatch"):
        verify(encoded_manifest(signature=sig, key="signer-02", inspection=manifest),
               {"signer-02": public_bytes})


def test_real_ed25519_signed_payload_denies_path_escape_even_with_valid_signature():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
    private = Ed25519PrivateKey.generate()
    key = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    malicious = payload(files=[{"path": "../outside.py", "sha256": "0" * 64}])
    sig = base64.b64encode(private.sign(
        signed_preview_bytes(key_id="signer-01", payload=malicious)
    )).decode("ascii")
    with pytest.raises(ValueError, match="Source path"):
        verify(encoded_manifest(signature=sig, inspection=malicious), {"signer-01": key})
