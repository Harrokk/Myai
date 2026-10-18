"""Adversarial test-only signing keys; production module has NO signer.

The checker does not authorize upgrades even if a test fixture signs a result.
"""
import json

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_signed_evidence import (
    AUDIENCE, ISSUER, DOMAIN, EvidenceInspection,
    canonical_statement_bytes, inspect_signed_evidence,
)

NOW = 1_800_000_000
SESSION = "session_1"
MANIFEST = "a" * 64
PLAN = "b" * 64
EVIDENCE = "c" * 64
CHALLENGE = "d" * 32


def payload(**overrides):
    value = {
        "version": 1, "purpose": "sandbox-verification-only",
        "issuer": ISSUER, "audience": AUDIENCE,
        "session_id": SESSION, "manifest_sha256": MANIFEST,
        "test_plan_sha256": PLAN, "evidence_sha256": EVIDENCE,
        "challenge": CHALLENGE, "verified_unix": NOW - 5,
        "expires_unix": NOW + 60, "passed": True,
        "sandbox": "bubblewrap", "network_isolated": True,
        "host_devices_exposed": False,
    }
    value.update(overrides)
    return value


def make_key():
    private = Ed25519PrivateKey.generate()  # TEST KEY ONLY, not a device secret
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return private, public


def sign(private, statement):
    signature = private.sign(canonical_statement_bytes(statement)).hex()
    return json.dumps(
        {"statement": statement, "signature": signature},
        separators=(",", ":"), sort_keys=True,
    ).encode()


def check(wire, public, **overrides):
    options = {
        "trusted_verifier_public_key": public,
        "expected_session_id": SESSION,
        "expected_manifest_sha256": MANIFEST,
        "expected_test_plan_sha256": PLAN,
        "expected_evidence_sha256": EVIDENCE,
        "expected_challenge": CHALLENGE,
        "now_unix": NOW,
    }
    options.update(overrides)
    return inspect_signed_evidence(wire, **options)


def test_correct_signed_bytes_match_only_returns_non_authorizing_inspection():
    secret, key = make_key()
    report = check(sign(secret, payload()), key)
    assert isinstance(report, EvidenceInspection)
    assert report.signature_verified is True
    assert report.source_provenance_verified is False
    assert report.independent_verifier_execution_verified is False
    assert report.durable_anti_replay_verified is False
    assert report.authorizes_mutation is False
    assert report.production_deployment_authorized is False
    with pytest.raises(AttributeError):
        report.authorizes_mutation = True


def test_equivalent_json_key_order_keeps_domain_separated_signature():
    private, public = make_key()
    statement = payload()
    wire = sign(private, statement)
    unpacked = json.loads(wire)
    shuffled = {"signature": unpacked["signature"], "statement": dict(reversed(list(statement.items())))}
    assert check(json.dumps(shuffled).encode(), public).signature_verified is True
    assert canonical_statement_bytes(statement).startswith(DOMAIN)


@pytest.mark.parametrize("patch", [
    {"passed": False}, {"sandbox": "host"}, {"network_isolated": False},
    {"host_devices_exposed": True}, {"version": 2},
    {"purpose": "promote"}, {"issuer": "untrusted-runtime"},
    {"audience": "myai-runtime"}, {"session_id": "../escape"},
    {"manifest_sha256": "A"*64}, {"test_plan_sha256": "x"*64},
    {"evidence_sha256": "0"}, {"challenge": "X"*32},
    {"verified_unix": True}, {"expires_unix": 0},
    {"verified_unix": NOW + 100}, {"expires_unix": NOW + 400},
])
def test_bad_assertions_cannot_be_signed_as_successful_evidence(patch):
    with pytest.raises(ValueError):
        canonical_statement_bytes(payload(**patch))


@pytest.mark.parametrize("extra", [
    "authorized", "promotion_enabled", "private_key", "production_release",
    "shell_command", "target_path", "verification_json", "signer_public_key",
])
def test_forbidden_extra_fields_rejected_even_before_signature(extra):
    with pytest.raises(ValueError):
        canonical_statement_bytes(payload(**{extra: True}))


@pytest.mark.parametrize("changes", [
    {"expected_session_id": "other-session"},
    {"expected_manifest_sha256": "0"*64},
    {"expected_test_plan_sha256": "1"*64},
    {"expected_evidence_sha256": "2"*64},
    {"expected_challenge": "3"*32},
])
def test_signed_payload_cannot_cross_trusted_context(changes):
    private, public = make_key()
    with pytest.raises(ValueError, match="context"):
        check(sign(private, payload()), public, **changes)


def test_test_signature_cannot_validate_against_different_pinned_public_key():
    private, _ = make_key()
    _, another = make_key()
    with pytest.raises(ValueError, match="signature"):
        check(sign(private, payload()), another)


@pytest.mark.parametrize("field,replacement", [
    ("passed", False),
    ("manifest_sha256", "f" * 64),
    ("challenge", "e" * 32),
    ("evidence_sha256", "f" * 64),
    ("verified_unix", NOW - 100),
])
def test_tampering_after_signing_is_rejected(field, replacement):
    private, key = make_key()
    value = json.loads(sign(private, payload()))
    value["statement"][field] = replacement
    with pytest.raises(ValueError):
        check(json.dumps(value).encode(), key)


@pytest.mark.parametrize("when", [
    NOW - 6,  # Future dated
    NOW + 60,  # Exactly expired
    NOW + 61,
])
def test_strict_time_binding_for_signed_evidence(when):
    private, key = make_key()
    with pytest.raises(ValueError):
        check(sign(private, payload()), key, now_unix=when)


def test_replay_challenge_supplied_by_updater_is_rejected():
    private, key = make_key()
    signed = sign(private, payload())
    with pytest.raises(ValueError, match="Replayed"):
        check(signed, key, used_challenges=frozenset({CHALLENGE}))
    # This alone is not a crash-safe replay database; the receipt says so.
    assert check(signed, key, used_challenges=()).durable_anti_replay_verified is False


@pytest.mark.parametrize("input_bytes", [
    b"", b"not-json", b"\xff", b"{}", b"[]",
    b'{"statement":1,"signature":"0","signature":"0"}',
    b'{"statement":NaN,"signature":"0"}',
    b"x" * 4097,
])
def test_bad_duplicate_nonfinite_or_large_envelopes_rejected(input_bytes):
    _, key = make_key()
    with pytest.raises(ValueError):
        check(input_bytes, key)


def test_extra_envelope_field_and_embedded_key_not_trusted():
    private, key = make_key()
    obj = json.loads(sign(private, payload()))
    obj["signer_public_key"] = key.hex()
    with pytest.raises(ValueError):
        check(json.dumps(obj).encode(), key)


def test_nested_duplicate_fields_cannot_hide_passing_flag():
    private, key = make_key()
    wire = sign(private, payload())
    wire = wire.replace(b'"passed":true', b'"passed":false,"passed":true')
    with pytest.raises(ValueError, match="Malformed"):
        check(wire, key)


@pytest.mark.parametrize("bad_key", [b"", b"\x00" * 31, "key", True, None])
def test_key_must_be_fixed_32_byte_raw_ed25519_public_key(bad_key):
    private, _ = make_key()
    with pytest.raises(ValueError):
        check(sign(private, payload()), bad_key)


@pytest.mark.parametrize("bad_nonce", [True, 0, "A"*32, "x", None])
def test_bad_trusted_challenges_rejected(bad_nonce):
    private, public = make_key()
    with pytest.raises(ValueError):
        check(sign(private, payload()), public, expected_challenge=bad_nonce)


@pytest.mark.parametrize("replay_state", [
    [CHALLENGE], {"bad": "mapping"}, [True], ["zz" * 16],
])
def test_untrusted_or_unsupported_replay_state_not_treated_as_durable(replay_state):
    private, public = make_key()
    with pytest.raises(ValueError):
        check(sign(private, payload()), public, used_challenges=replay_state)


def test_untrusted_successful_verification_json_is_not_signed_evidence():
    _, public = make_key()
    legacy = json.dumps({
        "passed": True, "returncode": 0, "sandbox": "bubblewrap",
        "network_isolated": True, "host_devices_exposed": False,
    }).encode()
    with pytest.raises(ValueError):
        check(legacy, public)


def test_has_no_key_generation_writer_or_promotion_entrypoint_in_production(monkeypatch):
    from pathlib import Path
    import core.selfdev_signed_evidence as module
    source = Path(module.__file__).read_text(encoding="utf-8")
    assert "Ed25519PrivateKey" not in source
    assert "save_verification(" not in source
    assert "SelfDevPromotionManager" not in source
    assert "subprocess." not in source
    assert "systemctl" not in source
    assert "open(" not in source
    assert "inspect_signed_evidence(" in source
