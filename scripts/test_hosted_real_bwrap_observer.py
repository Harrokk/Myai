"""GitHub-HOSTED disposable test of an actual Bubblewrap observation.

Runs only with an explicit host-only gate. There is NO production signing
identity, no installed service, no real MyAI tests, no selfdev promotion.
The Ed25519 key is an ephemeral test key in this single process.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import sqlite3
import tempfile
import time

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_bwrap_observation import (
    FIXTURE, FIXTURE_SHA256, PLAN_SHA256, observe,
)
from core.selfdev_signed_evidence import (
    ISSUER, AUDIENCE, canonical_statement_bytes,
)
from core.selfdev_attestation_replay import (
    initialize_ledger, issue_inspection_challenge, consume_signed_inspection,
)


def main():
    if (os.name != "posix"
            or os.environ.get("MYAI_HOSTED_BWRAP_TEST") != "yes"
            or os.environ.get("MYAI_RUNNER_ENVIRONMENT") != "github-hosted"
            or os.geteuid() == 0):
        raise RuntimeError("Refusing to run outside explicitly hosted unprivileged fixture")

    with tempfile.TemporaryDirectory(prefix="myai-real-bwrap-", dir="/tmp") as temp:
        root = Path(temp)
        root.chmod(0o700)
        sandbox = root / "fixture"
        sandbox.mkdir(mode=0o700)
        fixture = sandbox / "fixture.py"
        fixture.write_bytes(FIXTURE)
        fixture.chmod(0o600)

        # This raises on ANY Bubblewrap absence, namespace failure, wrong
        # return status, writable source, missing network isolation or drift.
        observed = observe(trusted_fixture_root=sandbox)

        # The remaining steps exercise the existing inspection-only signature
        # and atomic nonce ledger. This is NOT a distinct trusted verifier UID.
        evidence_digest = hashlib.sha256(
            b"MyAI/disposable-real-bwrap-observation/v1\0"
            + bytes.fromhex(observed.fixture_sha256)
            + bytes.fromhex(observed.plan_sha256)
        ).hexdigest()
        manifest_digest = hashlib.sha256(
            b"fixture.py:" + FIXTURE_SHA256.encode("ascii")
        ).hexdigest()
        db = sqlite3.connect(root / "nonce.sqlite", timeout=2)
        db.execute("PRAGMA synchronous=FULL")
        initialize_ledger(db)
        now = int(time.time())
        request = issue_inspection_challenge(
            db, session_id="hosted_bwrap_fixture_1",
            manifest_sha256=manifest_digest,
            test_plan_sha256=PLAN_SHA256,
            evidence_sha256=evidence_digest,
            now_unix=now, lifetime_seconds=60,
        )
        # Key is test-only and is generated only after a genuine successful
        # Bubblewrap run. It never leaves memory as private material.
        key = Ed25519PrivateKey.generate()
        pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
        record = {
            "version": 1, "purpose": "sandbox-verification-only",
            "issuer": ISSUER, "audience": AUDIENCE,
            "session_id": "hosted_bwrap_fixture_1",
            "manifest_sha256": manifest_digest,
            "test_plan_sha256": PLAN_SHA256,
            "evidence_sha256": evidence_digest,
            "challenge": request.challenge,
            "verified_unix": now,
            "expires_unix": now + 50,
            "passed": True, "sandbox": "bubblewrap",
            "network_isolated": True, "host_devices_exposed": False,
        }
        wire = json.dumps({
            "statement": record,
            "signature": key.sign(canonical_statement_bytes(record)).hex(),
        }, separators=(",", ":"), sort_keys=True).encode("ascii")
        receipt = consume_signed_inspection(
            db, envelope=wire, trusted_verifier_public_key=pub,
            expected_challenge=request.challenge, now_unix=now,
        )
        assert receipt.signed_context_matched
        assert receipt.production_deployment_authorized is False
        assert receipt.independent_verifier_execution_verified is False
        db.close()
        reopened = sqlite3.connect(root / "nonce.sqlite", timeout=2)
        initialize_ledger(reopened)
        try:
            consume_signed_inspection(
                reopened, envelope=wire,
                trusted_verifier_public_key=pub,
                expected_challenge=request.challenge, now_unix=now + 1,
            )
        except ValueError:
            replay_blocked = True
        else:
            raise AssertionError("Replay after SQLite reopening was accepted")
        finally:
            reopened.close()
        assert replay_blocked
        print("MYAI_HOSTED_REAL_BWRAP_OBSERVATION_JSON=" + json.dumps({
            "status": "PASS",
            "real_bubblewrap_subprocess_executed": True,
            "sandbox_network_namespace_observed_distinct": True,
            "sandbox_source_mutation_denied": True,
            "test_only_ed25519_signature_verified": True,
            "sqlite_replay_after_reopen_denied": True,
            "trusted_independent_production_verifier": False,
            "production_signing_key_provisioned": False,
            "production_hardware_affected": False,
            "selfdev_promotion_authorized": False,
            "production_deployment_authorized": False,
        }, sort_keys=True))


if __name__ == "__main__":
    main()
