"""Temporary SQLite signer nonce tests. No real keys, device, root or network."""
import concurrent.futures
from dataclasses import FrozenInstanceError
import shutil
import sqlite3
import threading

import pytest

from core.selfdev_receipt_signer_nonce_ledger import (
    initialize_signer_candidate_nonce_ledger, claim_receipt_once,
)

NOW = 1_800_000_000
NONCE = "a"*32
DEVICE = "fixture_ventuno"
INTENT = "fixture_receipt_intent"
HEAD = "b"*64
EVENT = "c"*64


def connect(path):
    db = sqlite3.connect(path, timeout=5)
    db.execute("PRAGMA synchronous=FULL")
    initialize_signer_candidate_nonce_ledger(db)
    return db


def consume(db, **patch):
    values = {
        "challenge": NONCE, "device_id": DEVICE, "intent_id": INTENT,
        "signed_witness_head_sha256": HEAD, "journal_event_sha256": EVENT,
        "now_unix": NOW, "expires_unix": NOW+60,
    }
    values.update(patch)
    return claim_receipt_once(db, **values)


def test_signature_nonce_record_is_committed_once_before_signature(tmp_path):
    db = connect(tmp_path/"signer-owned-test.db")
    try:
        status = consume(db)
        assert status.signer_owned_candidate_recorded is True
        assert status.actual_receipt_delivered is False
        assert status.independent_external_checkpoint_advanced is False
        assert status.power_loss_rollback_resistance_verified is False
        assert status.authorizes_mutation is False
        assert status.production_deployment_authorized is False
        with pytest.raises(FrozenInstanceError):
            status.production_deployment_authorized = True
        with pytest.raises(ValueError, match="already consumed"):
            consume(db)
        with pytest.raises(ValueError, match="already consumed"):
            consume(db, signed_witness_head_sha256="d"*64)
        assert not db.in_transaction
        assert db.execute(
            "SELECT COUNT(*) FROM candidate_signer_consumed_receipts"
        ).fetchone()[0] == 1
    finally:
        db.close()


def test_sqlite_reopen_preserves_consumed_nonce(tmp_path):
    path = tmp_path/"signer-state.sqlite"
    db = connect(path)
    consume(db)
    db.close()
    reopened = connect(path)
    try:
        with pytest.raises(ValueError, match="already consumed"):
            consume(reopened)
    finally:
        reopened.close()


def test_two_connections_cannot_both_claim_same_nonce(tmp_path):
    path = tmp_path/"claim.sqlite"
    c = connect(path)
    c.close()
    gate = threading.Barrier(2)
    def attempt():
        db = connect(path)
        try:
            gate.wait(timeout=4)
            try:
                consume(db)
                return "consumed"
            except ValueError:
                return "denied"
        finally:
            db.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [f.result(timeout=10) for f in (
            pool.submit(attempt), pool.submit(attempt)
        )]
    assert sorted(outcomes) == ["consumed", "denied"]


@pytest.mark.parametrize("patch", [
    {"challenge":"A"*32}, {"challenge":True}, {"device_id":"../prod"},
    {"intent_id":"other/dir"}, {"signed_witness_head_sha256":"Z"*64},
    {"journal_event_sha256":"0"*63}, {"now_unix":True},
    {"now_unix":-1}, {"expires_unix":NOW}, {"expires_unix":NOW+121},
    {"expires_unix":True},
])
def test_bad_candidate_signing_context_never_consumes(tmp_path, patch):
    db = connect(tmp_path/"bad.sqlite")
    try:
        with pytest.raises(ValueError):
            consume(db, **patch)
        assert not db.in_transaction
        assert db.execute(
            "SELECT count(*) FROM candidate_signer_consumed_receipts"
        ).fetchone()[0] == 0
    finally:
        db.close()


def test_rollback_old_db_without_external_anchor_could_resign(tmp_path):
    path = tmp_path/"new.sqlite"
    stale = tmp_path/"stale.sqlite"
    db = connect(path)
    db.close()
    shutil.copyfile(path, stale)
    db = connect(path)
    consume(db)
    db.close()
    old_db = connect(stale)
    try:
        # This is a deliberately NEGATIVE result: a copied SQLite DB with
        # missing consumed nonce offers no monotonic anti-rollback proof.
        assert consume(old_db).independent_external_checkpoint_advanced is False
        assert not old_db.in_transaction
    finally:
        old_db.close()


def test_source_is_no_signer_no_installer_and_no_db_path_creation():
    from pathlib import Path
    import core.selfdev_receipt_signer_nonce_ledger as mod
    s = Path(mod.__file__).read_text()
    for dangerous in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager", "os.chown(",
        "save_verification(",
    ):
        assert dangerous not in s
    assert "production_deployment_authorized: bool = False" in s
