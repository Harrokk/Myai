"""Pure trust-pin and lifecycle tests, with temporary Ed25519 only on host."""

import base64
from dataclasses import replace
import hashlib
import json

import pytest

from core.selfdev_preview_trust_policy import (
    PreviewSignerPolicy,
    active_preview_public_keys,
    verify_preview_with_signer_policy,
)
from core.selfdev_signed_manifest import signed_preview_bytes


NOW = 1800000000
KEY_A = b"\x03" * 32
KEY_B = b"\x04" * 32


def _record(name, key, start=NOW - 100, until=NOW + 100, revoked=False):
    return PreviewSignerPolicy(name, key, start, until, revoked)


def _pins(records):
    return {r.key_id: hashlib.sha256(r.public_key).hexdigest() for r in records}


def _select(records, **kwargs):
    pins = kwargs.pop("pinned_fingerprints", _pins(records))
    now = kwargs.pop("now_unix", NOW)
    return active_preview_public_keys(
        records, pinned_fingerprints=pins, now_unix=now, **kwargs
    )


def test_active_key_provided_only_from_separately_pinned_policy():
    record = _record("key-old", KEY_A)
    assert _select((record,)) == {"key-old": KEY_A}


def test_overlapping_key_rotation_permits_both_valid_signers():
    old = _record("key-old", KEY_A, NOW - 400, NOW + 5)
    newer = _record("key-new", KEY_B, NOW - 5, NOW + 400)
    assert _select((old, newer)) == {"key-old": KEY_A, "key-new": KEY_B}
    assert _select((old, newer), now_unix=NOW + 6) == {"key-new": KEY_B}


def test_revocation_is_irreversible_within_the_trusted_policy():
    old = _record("key-old", KEY_A, revoked=True)
    newer = _record("key-new", KEY_B)
    assert _select((old, newer), now_unix=NOW - 5) == {"key-new": KEY_B}
    assert _select((old, newer), now_unix=NOW + 5) == {"key-new": KEY_B}


def test_revoked_only_key_fails_closed_without_fallback():
    with pytest.raises(ValueError, match="No currently active"):
        _select((_record("revoked", KEY_A, revoked=True),))


def test_before_activation_and_expired_key_are_not_accepted():
    future = _record("key-new", KEY_A, NOW + 1, NOW + 100)
    with pytest.raises(ValueError, match="No currently active"):
        _select((future,))
    expired = _record("key-old", KEY_A, NOW - 100, NOW)
    with pytest.raises(ValueError, match="No currently active"):
        _select((expired,))


def test_validity_range_is_half_open_at_both_edges():
    record = _record("key-old", KEY_A, NOW, NOW + 1)
    assert _select((record,)) == {"key-old": KEY_A}
    with pytest.raises(ValueError, match="No currently active"):
        _select((record,), now_unix=NOW + 1)


def test_unknown_or_missing_pinned_identity_is_rejected():
    record = _record("key-old", KEY_A)
    with pytest.raises(ValueError, match="differs"):
        _select((record,), pinned_fingerprints={})
    with pytest.raises(ValueError, match="differs"):
        _select((record,), pinned_fingerprints={
            **_pins((record,)), "attacker": "a" * 64,
        })


def test_unpinned_or_edited_public_key_cannot_extend_trust():
    old = _record("key-old", KEY_A)
    forged = replace(old, public_key=KEY_B)
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        _select((forged,), pinned_fingerprints=_pins((old,)))


def test_duplicate_signer_ids_and_reused_public_key_rejected():
    with pytest.raises(ValueError, match="Duplicate"):
        _select((_record("key-old", KEY_A), _record("key-old", KEY_B)))
    with pytest.raises(ValueError, match="reused"):
        _select((_record("key-old", KEY_A), _record("key-new", KEY_A)))


@pytest.mark.parametrize("invalid", [
    True, -1, 1.0, "timestamp", None,
])
def test_untrusted_clock_values_rejected(invalid):
    with pytest.raises(ValueError, match="clock"):
        _select((_record("key-old", KEY_A),), now_unix=invalid)


@pytest.mark.parametrize("bad", [
    _record("key-old", b"short"),
    _record("key-old", KEY_A, NOW, NOW),
    _record("key-old", KEY_A, -1, NOW),
    _record("key-old", KEY_A, NOW + 1, NOW),
    _record("key-old", KEY_A, revoked=1),
    _record("../evil", KEY_A),
])
def test_invalid_key_records_fail_before_use(bad):
    with pytest.raises(ValueError):
        _select((bad,))


def test_no_policy_record_fails_closed():
    with pytest.raises(ValueError, match="records"):
        _select(())


def test_actual_crypto_key_rotated_and_revoked_denies_its_signed_manifest():
    pytest.importorskip("cryptography")
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

    old_private = Ed25519PrivateKey.generate()
    next_private = Ed25519PrivateKey.generate()
    def pub(key):
        return key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)

    old_record = _record("key-old", pub(old_private))
    next_record = _record("key-new", pub(next_private))
    records = (old_record, next_record)
    pins = _pins(records)
    payload = {
        "version": 1,
        "action": "inspect_candidate",
        "request_id": "a" * 32,
        "revision": "b" * 40,
        "expires_unix": NOW + 60,
        "files": [{
            "path": "core/example.py",
            "sha256": hashlib.sha256(b"contents").hexdigest(),
        }],
    }

    def sign(key, name):
        signature = base64.b64encode(
            key.sign(signed_preview_bytes(key_id=name, payload=payload))
        ).decode("ascii")
        return json.dumps({
            "version": 1, "algorithm": "Ed25519",
            "key_id": name, "payload": payload, "signature": signature,
        }).encode("utf-8")

    old_signed = sign(old_private, "key-old")
    new_signed = sign(next_private, "key-new")
    assert verify_preview_with_signer_policy(
        old_signed, records, pinned_fingerprints=pins, now_unix=NOW,
    ).authorizes_mutation is False
    assert verify_preview_with_signer_policy(
        new_signed, records, pinned_fingerprints=pins, now_unix=NOW,
    ).authorizes_mutation is False

    revoked_records = (replace(old_record, revoked=True), next_record)
    with pytest.raises(ValueError, match="trusted"):
        verify_preview_with_signer_policy(
            old_signed, revoked_records, pinned_fingerprints=pins, now_unix=NOW
        )
    assert verify_preview_with_signer_policy(
        new_signed, revoked_records, pinned_fingerprints=pins, now_unix=NOW
    ).signature_valid is True
