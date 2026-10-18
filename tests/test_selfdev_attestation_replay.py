"""All ledger tests use temporary/offline SQLite and throwaway signing keys."""
import json
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_signed_evidence import (
    ISSUER, AUDIENCE, canonical_statement_bytes,
)
from core.selfdev_attestation_replay import (
    initialize_ledger, issue_inspection_challenge, consume_signed_inspection,
)

NOW = 1_800_000_000
SESSION = "session_1"
MANIFEST = "a" * 64
PLAN = "b" * 64
EVIDENCE = "c" * 64
CHALLENGE = "d" * 32


def connection(path):
    conn = sqlite3.connect(path, timeout=1)
    conn.execute("PRAGMA synchronous=FULL")
    initialize_ledger(conn)
    return conn


def issue(db, **kwargs):
    args = dict(
        session_id=SESSION, manifest_sha256=MANIFEST,
        test_plan_sha256=PLAN, evidence_sha256=EVIDENCE,
        now_unix=NOW, nonce_factory=lambda size: CHALLENGE,
    )
    args.update(kwargs)
    return issue_inspection_challenge(db, **args)


def sign_for_test(private, challenge=CHALLENGE, **patches):
    statement = {
        "version": 1, "purpose": "sandbox-verification-only",
        "issuer": ISSUER, "audience": AUDIENCE,
        "session_id": SESSION, "manifest_sha256": MANIFEST,
        "test_plan_sha256": PLAN, "evidence_sha256": EVIDENCE,
        "challenge": challenge, "verified_unix": NOW,
        "expires_unix": NOW + 60, "passed": True,
        "sandbox": "bubblewrap", "network_isolated": True,
        "host_devices_exposed": False,
    }
    statement.update(patches)
    return json.dumps({
        "statement": statement,
        "signature": private.sign(canonical_statement_bytes(statement)).hex(),
    }, separators=(",", ":")).encode()


def test_issue_and_consume_signed_context_is_not_promotion(tmp_path):
    with connection(tmp_path / "ledger.db") as db:
        challenge = issue(db)
        assert challenge.challenge == CHALLENGE
        assert challenge.authorizes_mutation is False
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        result = consume_signed_inspection(
            db, envelope=sign_for_test(private),
            trusted_verifier_public_key=public,
            expected_challenge=CHALLENGE, now_unix=NOW + 1,
        )
        assert result.signed_context_matched is True
        assert result.independent_verifier_execution_verified is False
        assert result.authorizes_mutation is False
        assert result.production_deployment_authorized is False


def test_replay_denied_after_close_and_reopen_file_database(tmp_path):
    path = tmp_path / "persisted.db"
    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    db = connection(path)
    issue(db)
    first = consume_signed_inspection(
        db, envelope=sign_for_test(private),
        trusted_verifier_public_key=public,
        expected_challenge=CHALLENGE, now_unix=NOW + 1,
    )
    assert first.challenge == CHALLENGE
    db.close()
    db = connection(path)
    try:
        with pytest.raises(ValueError, match="consumed"):
            consume_signed_inspection(
                db, envelope=sign_for_test(private),
                trusted_verifier_public_key=public,
                expected_challenge=CHALLENGE, now_unix=NOW + 2,
            )
    finally:
        db.close()


def test_signed_evidence_replay_denied_across_two_connections(tmp_path):
    path = tmp_path / "shared.db"
    first, second = connection(path), connection(path)
    try:
        issue(first)
        private = Ed25519PrivateKey.generate()
        public = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        signed = sign_for_test(private)
        consume_signed_inspection(
            first, envelope=signed, trusted_verifier_public_key=public,
            expected_challenge=CHALLENGE, now_unix=NOW + 1,
        )
        with pytest.raises(ValueError, match="consumed"):
            consume_signed_inspection(
                second, envelope=signed, trusted_verifier_public_key=public,
                expected_challenge=CHALLENGE, now_unix=NOW + 1,
            )
    finally:
        first.close()
        second.close()


def test_duplicate_nonce_was_never_silently_reissued(tmp_path):
    db = connection(tmp_path / "ledger.db")
    try:
        issue(db)
        with pytest.raises(sqlite3.IntegrityError):
            issue(db)
        assert db.in_transaction is False
        assert db.execute("SELECT count(*) FROM inspection_challenges").fetchone()[0] == 1
    finally:
        db.close()


@pytest.mark.parametrize("field,value", [
    ("session_id", "other-session"), ("manifest_sha256", "f" * 64),
    ("test_plan_sha256", "f" * 64), ("evidence_sha256", "f" * 64),
])
def test_signed_wrong_context_does_not_consume_nonce(tmp_path, field, value):
    db = connection(tmp_path / "ledger.db")
    try:
        issue(db)
        private = Ed25519PrivateKey.generate()
        pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        wire = sign_for_test(private, **{field: value})
        with pytest.raises(ValueError):
            consume_signed_inspection(
                db, envelope=wire, trusted_verifier_public_key=pub,
                expected_challenge=CHALLENGE, now_unix=NOW + 1,
            )
        assert db.execute(
            "SELECT consumed_unix FROM inspection_challenges"
        ).fetchone()[0] is None
        assert db.in_transaction is False
    finally:
        db.close()


def test_wrong_key_then_good_key_consumes_only_good_evidence(tmp_path):
    db = connection(tmp_path / "ledger.db")
    try:
        issue(db)
        good = Ed25519PrivateKey.generate()
        bad = Ed25519PrivateKey.generate()
        key = good.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        with pytest.raises(ValueError):
            consume_signed_inspection(
                db, envelope=sign_for_test(bad),
                trusted_verifier_public_key=key,
                expected_challenge=CHALLENGE, now_unix=NOW + 1,
            )
        result = consume_signed_inspection(
            db, envelope=sign_for_test(good),
            trusted_verifier_public_key=key,
            expected_challenge=CHALLENGE, now_unix=NOW + 2,
        )
        assert result.challenge == CHALLENGE
    finally:
        db.close()


@pytest.mark.parametrize("now", [NOW - 1, NOW + 120, NOW + 121])
def test_stale_or_not_yet_issued_nonce_denied(tmp_path, now):
    db = connection(tmp_path / "ledger.db")
    try:
        issue(db)
        private = Ed25519PrivateKey.generate()
        pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        with pytest.raises(ValueError, match="Stale"):
            consume_signed_inspection(
                db, envelope=sign_for_test(private),
                trusted_verifier_public_key=pub,
                expected_challenge=CHALLENGE, now_unix=now,
            )
    finally:
        db.close()


@pytest.mark.parametrize("lifetime", [0, -1, 301, True, 1.0, "120"])
def test_bad_challenge_lifetime_never_writes_record(tmp_path, lifetime):
    db = connection(tmp_path / "ledger.db")
    try:
        with pytest.raises(ValueError):
            issue(db, lifetime_seconds=lifetime)
        assert db.execute("SELECT count(*) FROM inspection_challenges").fetchone()[0] == 0
    finally:
        db.close()


def test_consumption_denies_unknown_challenge_even_with_valid_signature(tmp_path):
    db = connection(tmp_path / "ledger.db")
    try:
        private = Ed25519PrivateKey.generate()
        pub = private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        with pytest.raises(ValueError, match="Missing"):
            consume_signed_inspection(
                db, envelope=sign_for_test(private),
                trusted_verifier_public_key=pub,
                expected_challenge=CHALLENGE, now_unix=NOW,
            )
    finally:
        db.close()


def test_issue_rejects_caller_chosen_invalid_nonce(tmp_path):
    db = connection(tmp_path / "ledger.db")
    try:
        with pytest.raises(ValueError):
            issue(db, nonce_factory=lambda size: "A" * 32)
        assert db.execute("SELECT count(*) FROM inspection_challenges").fetchone()[0] == 0
    finally:
        db.close()


def test_schema_api_only_uses_supplied_sqlite_connection_and_no_promotion():
    from pathlib import Path
    import core.selfdev_attestation_replay as code
    source = Path(code.__file__).read_text(encoding="utf-8")
    assert "sqlite3.connect(" not in source
    assert "Ed25519PrivateKey" not in source
    assert "save_verification(" not in source
    assert "SelfDevPromotionManager" not in source
    assert "systemctl" not in source
    assert "subprocess." not in source
    assert "authorizes_mutation: bool = False" in source
