"""Offline verification of *externally* signed selfdev evidence (NO promotion).

This module has NO signer/private key, writer, network, process or deployment
operation. A trusted verifier on a different OS identity is still REQUIRED
and NOT implemented. An Ed25519 signature alone does NOT prove a test ran.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
import time

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey


DOMAIN = b"MyAI/selfdev/independent-sandbox-evidence/v1\0"
MAX_ENVELOPE = 4096
MAX_LIFETIME = 300
HEX32 = re.compile(r"[0-9a-f]{32}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
HEX128 = re.compile(r"[0-9a-f]{128}\Z")
SESSION = re.compile(r"[A-Za-z0-9_-]{1,96}\Z")
FIELDS = frozenset({
    "version", "purpose", "issuer", "audience", "session_id",
    "manifest_sha256", "test_plan_sha256", "evidence_sha256",
    "challenge", "verified_unix", "expires_unix", "passed",
    "sandbox", "network_isolated", "host_devices_exposed",
})
ISSUER = "myai-independent-verifier-v1"
AUDIENCE = "myai-updater-inspection-only"


@dataclass(frozen=True)
class EvidenceInspection:
    """Non-promoting result; replay checks are only caller-supplied hints."""

    session_id: str
    manifest_sha256: str
    evidence_sha256: str
    challenge: str
    signature_verified: bool = True
    source_provenance_verified: bool = False
    independent_verifier_execution_verified: bool = False
    durable_anti_replay_verified: bool = False
    authorizes_mutation: bool = False
    production_deployment_authorized: bool = False


def _object_no_duplicates(pairs):
    value = {}
    for k, v in pairs:
        if k in value:
            raise ValueError("Duplicate field")
        value[k] = v
    return value


def _forbid_constant(value):
    raise ValueError("Nonfinite number")


def _expect_digest(value, label):
    if type(value) is not str or HEX64.fullmatch(value) is None:
        raise ValueError("Invalid " + label)
    return value


def _expect_challenge(value):
    if type(value) is not str or HEX32.fullmatch(value) is None:
        raise ValueError("Invalid challenge")
    return value


def canonical_statement_bytes(statement):
    """Canonical domain-separated signature input; no unknown field accepted."""
    if type(statement) is not dict or set(statement) != FIELDS:
        raise ValueError("Unrecognized evidence fields")
    if type(statement["version"]) is not int or statement["version"] != 1:
        raise ValueError("Unsupported evidence version")
    if (statement["purpose"] != "sandbox-verification-only"
            or statement["issuer"] != ISSUER
            or statement["audience"] != AUDIENCE):
        raise ValueError("Wrong evidence domain")
    if (type(statement["session_id"]) is not str
            or SESSION.fullmatch(statement["session_id"]) is None):
        raise ValueError("Invalid session identity")
    for label in ("manifest_sha256", "test_plan_sha256", "evidence_sha256"):
        _expect_digest(statement[label], label)
    _expect_challenge(statement["challenge"])
    if (type(statement["verified_unix"]) is not int
            or type(statement["expires_unix"]) is not int
            or statement["verified_unix"] < 0
            or not statement["verified_unix"] < statement["expires_unix"]
            or statement["expires_unix"] - statement["verified_unix"] > MAX_LIFETIME):
        raise ValueError("Invalid signed lifetime")
    if (statement["passed"] is not True
            or statement["sandbox"] != "bubblewrap"
            or statement["network_isolated"] is not True
            or statement["host_devices_exposed"] is not False):
        raise ValueError("No successful isolated execution attested")
    return DOMAIN + json.dumps(
        statement, ensure_ascii=True, sort_keys=True, separators=(",", ":"),
        allow_nan=False,
    ).encode("ascii")


def inspect_signed_evidence(
    envelope, *, trusted_verifier_public_key, expected_session_id,
    expected_manifest_sha256, expected_test_plan_sha256,
    expected_evidence_sha256, expected_challenge, now_unix=None,
    used_challenges=(),
):
    """Verify signature and strict context; NEVER accept keys from envelope.

    Trusted inputs MUST be obtained independently from updater-owned state.
    used_challenges is a caller-provided *non-durable* replay hint; callers
    still need a crash-safe updater-owned ledger and independent signing
    service. Returning a receipt NEVER permits promotion.
    """
    if type(envelope) is not bytes or not 0 < len(envelope) <= MAX_ENVELOPE:
        raise ValueError("Invalid or oversized evidence envelope")
    if type(trusted_verifier_public_key) is not bytes or len(trusted_verifier_public_key) != 32:
        raise ValueError("Trusted Ed25519 public key must be pinned out-of-band")
    if (type(expected_session_id) is not str
            or SESSION.fullmatch(expected_session_id) is None):
        raise ValueError("Bad trusted session")
    for label, value in (
        ("manifest", expected_manifest_sha256),
        ("plan", expected_test_plan_sha256),
        ("evidence", expected_evidence_sha256),
    ):
        _expect_digest(value, "trusted " + label)
    _expect_challenge(expected_challenge)
    if type(used_challenges) not in (frozenset, set, tuple):
        raise ValueError("Invalid replay challenge collection")
    if any(type(c) is not str or HEX32.fullmatch(c) is None for c in used_challenges):
        raise ValueError("Malformed replay challenge")
    if expected_challenge in used_challenges:
        raise ValueError("Replayed challenge")
    now = int(time.time()) if now_unix is None else now_unix
    if type(now) is not int or now < 0:
        raise ValueError("Invalid current time")
    try:
        parsed = json.loads(
            envelope.decode("utf-8"),
            object_pairs_hook=_object_no_duplicates,
            parse_constant=_forbid_constant,
        )
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("Malformed signed evidence") from error
    if type(parsed) is not dict or set(parsed) != {"statement", "signature"}:
        raise ValueError("Unknown envelope fields")
    payload = parsed["statement"]
    signed = canonical_statement_bytes(payload)
    sig = parsed["signature"]
    if type(sig) is not str or HEX128.fullmatch(sig) is None:
        raise ValueError("Malformed Ed25519 signature")
    # Verify key is passed from trusted updater configuration, NEVER from
    # untrusted JSON; reject altered or unsigned evidence before evaluation.
    try:
        Ed25519PublicKey.from_public_bytes(trusted_verifier_public_key).verify(
            bytes.fromhex(sig), signed,
        )
    except (InvalidSignature, ValueError) as error:
        raise ValueError("Invalid evidence signature") from error
    if (
        payload["session_id"] != expected_session_id
        or payload["manifest_sha256"] != expected_manifest_sha256
        or payload["test_plan_sha256"] != expected_test_plan_sha256
        or payload["evidence_sha256"] != expected_evidence_sha256
        or payload["challenge"] != expected_challenge
    ):
        raise ValueError("Evidence does not match trusted updater context")
    if not payload["verified_unix"] <= now < payload["expires_unix"]:
        raise ValueError("Evidence expired or dated in the future")
    return EvidenceInspection(
        session_id=payload["session_id"],
        manifest_sha256=payload["manifest_sha256"],
        evidence_sha256=payload["evidence_sha256"],
        challenge=payload["challenge"],
    )
