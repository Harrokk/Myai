"""Updater-side, inspection-only, SQLite nonce ledger prototype.

Caller supplies an updater-owned SQLite connection and a trusted verifier
public key; this module cannot create a service, private key, file path,
start tests, sign evidence or promote code. A live separate UID and safe DB
storage are NOT established by this source module.
"""
from __future__ import annotations

from dataclasses import dataclass
import secrets
import sqlite3

from core.selfdev_signed_evidence import (
    MAX_LIFETIME, HEX32, SESSION, _expect_digest,
    inspect_signed_evidence,
)


@dataclass(frozen=True)
class PendingChallenge:
    challenge: str
    expires_unix: int
    authorizes_mutation: bool = False


@dataclass(frozen=True)
class ConsumedEvidence:
    challenge: str
    session_id: str
    signed_context_matched: bool = True
    independent_verifier_execution_verified: bool = False
    production_deployment_authorized: bool = False
    authorizes_mutation: bool = False


_SCHEMA = """
CREATE TABLE IF NOT EXISTS inspection_challenges (
  challenge TEXT PRIMARY KEY NOT NULL,
  session_id TEXT NOT NULL,
  manifest_sha256 TEXT NOT NULL,
  test_plan_sha256 TEXT NOT NULL,
  evidence_sha256 TEXT NOT NULL,
  issued_unix INTEGER NOT NULL,
  expires_unix INTEGER NOT NULL,
  consumed_unix INTEGER,
  CHECK (length(challenge) = 32),
  CHECK (expires_unix > issued_unix),
  CHECK (expires_unix - issued_unix <= 300)
)
"""


def initialize_ledger(connection):
    """Only accepts an already-authorized connection; never opens a DB path."""
    if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
        raise ValueError("Dedicated updater SQLite connection required")
    connection.execute(_SCHEMA)
    connection.commit()


def _begin(connection):
    if not isinstance(connection, sqlite3.Connection) or connection.in_transaction:
        raise ValueError("No pending transaction allowed")
    connection.execute("BEGIN IMMEDIATE")


def _valid_context(session_id, manifest_sha256, test_plan_sha256,
                   evidence_sha256, now_unix):
    if type(session_id) is not str or SESSION.fullmatch(session_id) is None:
        raise ValueError("Invalid updater session")
    for label, value in (
        ("manifest", manifest_sha256), ("plan", test_plan_sha256),
        ("evidence", evidence_sha256),
    ):
        _expect_digest(value, label)
    if type(now_unix) is not int or now_unix < 0:
        raise ValueError("Invalid clock")


def issue_inspection_challenge(
    connection, *, session_id, manifest_sha256, test_plan_sha256,
    evidence_sha256, now_unix, lifetime_seconds=120,
    nonce_factory=secrets.token_hex,
):
    """Issue one independent updater nonce bound to exact inspection inputs.

    nonce_factory is injectable solely for deterministic tests. A real updater
    must never let a remote/runtime caller choose it or choose DB connection.
    """
    _valid_context(session_id, manifest_sha256, test_plan_sha256,
                   evidence_sha256, now_unix)
    if (type(lifetime_seconds) is not int
            or not 1 <= lifetime_seconds <= MAX_LIFETIME):
        raise ValueError("Invalid challenge duration")
    nonce = nonce_factory(16)
    if type(nonce) is not str or HEX32.fullmatch(nonce) is None:
        raise ValueError("Invalid updater-generated nonce")
    _begin(connection)
    try:
        connection.execute(
            """INSERT INTO inspection_challenges
            (challenge,session_id,manifest_sha256,test_plan_sha256,
             evidence_sha256,issued_unix,expires_unix)
            VALUES (?,?,?,?,?,?,?)""",
            (nonce, session_id, manifest_sha256, test_plan_sha256,
             evidence_sha256, now_unix, now_unix + lifetime_seconds),
        )
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return PendingChallenge(nonce, now_unix + lifetime_seconds)


def consume_signed_inspection(
    connection, *, envelope, trusted_verifier_public_key,
    expected_challenge, now_unix,
):
    """Atomically consume a valid bound nonce once; never authorize promotion.

    A different worker/process can use the same SQLite DB; BEGIN IMMEDIATE
    serializes cooperating writers. A malicious same-UID writer can still
    replace a poorly protected DB, so this is NOT live privilege proof.
    """
    if (type(expected_challenge) is not str
            or HEX32.fullmatch(expected_challenge) is None
            or type(now_unix) is not int or now_unix < 0):
        raise ValueError("Invalid trusted challenge or clock")
    _begin(connection)
    try:
        row = connection.execute(
            """SELECT session_id,manifest_sha256,test_plan_sha256,
                      evidence_sha256,issued_unix,expires_unix,consumed_unix
               FROM inspection_challenges WHERE challenge=?""",
            (expected_challenge,),
        ).fetchone()
        if row is None or row[6] is not None:
            raise ValueError("Missing or consumed inspection challenge")
        session_id, manifest, plan, evidence, issued, expiry, _ = row
        if (type(issued) is not int or type(expiry) is not int
                or not issued <= now_unix < expiry):
            raise ValueError("Stale updater challenge")
        receipt = inspect_signed_evidence(
            envelope,
            trusted_verifier_public_key=trusted_verifier_public_key,
            expected_session_id=session_id,
            expected_manifest_sha256=manifest,
            expected_test_plan_sha256=plan,
            expected_evidence_sha256=evidence,
            expected_challenge=expected_challenge,
            now_unix=now_unix,
        )
        cursor = connection.execute(
            """UPDATE inspection_challenges SET consumed_unix=?
               WHERE challenge=? AND consumed_unix IS NULL""",
            (now_unix, expected_challenge),
        )
        if cursor.rowcount != 1:
            raise ValueError("Concurrent replay denied")
        connection.commit()
    except BaseException:
        connection.rollback()
        raise
    return ConsumedEvidence(receipt.challenge, receipt.session_id)
