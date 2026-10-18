"""Offline crash-cutpoint matrix: only temporary SQLite and ephemeral witness keys."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_recovery_consistency import (
    RecoveryInspection, inspect_recovery_consistency,
)
from core.selfdev_signed_witness_checkpoint import (
    ISSUER, PURPOSE, AUDIENCE, canonical_witness_checkpoint,
)
from core.selfdev_verifier_key_state_preview import (
    initialize_candidate_schema, seed_candidate_for_test,
)
from core.selfdev_operator_nonce_ledger import initialize_operator_review_ledger
from core.selfdev_verifier_key_rotation import TrustedVerifierKey

DEVICE = "myai_disposable_test"
NONCE = "a" * 32
AT = 1_800_000_000


def ephemeral():
    key = Ed25519PrivateKey.generate()
    pub = key.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return key, pub


def checkpoint(key, epoch, *, sequence, parent="0"*64, retired=(),
               consumed=(), at=AT):
    return {
        "version": 1,
        "issuer": ISSUER, "purpose": PURPOSE, "audience": AUDIENCE,
        "device_id": DEVICE, "sequence": sequence,
        "verifier_epoch": epoch,
        "verifier_public_key_hex": key.hex(),
        "verifier_fingerprint": hashlib.sha256(key).hexdigest(),
        "retired_verifier_fingerprints": sorted(retired),
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": parent,
        "recorded_unix": at,
    }


def sign(secret, document):
    canonical = canonical_witness_checkpoint(document)
    return (json.dumps({
        "statement": document, "signature": secret.sign(canonical).hex(),
    }, sort_keys=True, separators=(",", ":")).encode(),
            hashlib.sha256(canonical).hexdigest())


@pytest.fixture
def laboratory(tmp_path):
    signer, pub = ephemeral()
    _, initial = ephemeral()
    _, successor = ephemeral()
    gen, gen_sha = sign(signer, checkpoint(initial, 4, sequence=1))
    nonce_doc, nonce_sha = sign(signer, checkpoint(
        initial, 4, sequence=2, parent=gen_sha,
        consumed=(NONCE,), at=AT+1,
    ))
    final, final_sha = sign(signer, checkpoint(
        successor, 5, sequence=3, parent=nonce_sha,
        retired=(hashlib.sha256(initial).hexdigest(),),
        consumed=(NONCE,), at=AT+2,
    ))
    key_path = tmp_path / "candidate-key.sqlite"
    operator_path = tmp_path / "candidate-operator.sqlite"
    key_db = sqlite3.connect(key_path)
    op_db = sqlite3.connect(operator_path)
    initialize_candidate_schema(key_db)
    initialize_operator_review_ledger(op_db)
    seed_candidate_for_test(
        key_db, externally_pinned_initial_key=TrustedVerifierKey(initial, 4),
    )
    results = {
        "key_db": key_db, "op_db": op_db,
        "key_path": key_path, "operator_path": operator_path,
        "old": initial, "new": successor,
        "witness_pub": pub,
        "genesis": gen_sha, "heads": (gen_sha, nonce_sha, final_sha),
        "wires": (gen, nonce_doc, final),
    }
    yield results
    key_db.close()
    op_db.close()


def mutate_nonce(lab, consumed=True, device=DEVICE):
    db = lab["op_db"]
    db.execute(
        """INSERT INTO candidate_operator_challenges
           (challenge,device_id,old_epoch,old_fingerprint,
            new_fingerprint,rotation_sha256,operator_fingerprint,
            issued_unix,expires_unix,consumed_unix)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (NONCE, device, 4, hashlib.sha256(lab["old"]).hexdigest(),
         hashlib.sha256(lab["new"]).hexdigest(), "b"*64, "c"*64,
         AT, AT+60, AT+1 if consumed else None),
    )
    db.commit()


def mutate_key(lab):
    db = lab["key_db"]
    db.execute(
        """UPDATE candidate_verifier_state
           SET epoch=5, public_key=?,fingerprint=? WHERE singleton=1""",
        (lab["new"], hashlib.sha256(lab["new"]).hexdigest()),
    )
    db.execute(
        """INSERT INTO candidate_verifier_revoked(fingerprint,retired_at_epoch)
           VALUES (?,5)""",
        (hashlib.sha256(lab["old"]).hexdigest(),),
    )
    db.commit()


def recover(lab, index, **patches):
    kw = dict(
        candidate_key_db=lab["key_db"],
        candidate_operator_db=lab["op_db"],
        witness_envelopes=lab["wires"][:index+1],
        pinned_witness_public_key=lab["witness_pub"],
        pinned_genesis_sha256=lab["genesis"],
        pinned_latest_head_sha256=lab["heads"][index],
        expected_device_id=DEVICE,
    )
    kw.update(patches)
    return inspect_recovery_consistency(**kw)


def test_genesis_consistent_but_even_full_match_cannot_resume_or_deploy(laboratory):
    result = recover(laboratory, 0)
    assert isinstance(result, RecoveryInspection)
    assert result.candidate_views_equal_signed_witness is True
    assert result.manual_reconciliation_required is False
    assert result.differences == ()
    assert result.external_durable_commit_verified is False
    assert result.cross_database_atomic_snapshot_verified is False
    assert result.concurrent_writers_quiesced_verified is False
    assert result.independent_live_head_freshness_verified is False
    assert result.safe_to_resume_production is False
    assert result.automatic_repair_permitted is False
    assert result.authorizes_mutation is False
    assert result.production_deployment_authorized is False
    with pytest.raises(FrozenInstanceError):
        result.safe_to_resume_production = True


@pytest.mark.parametrize("stage,issues", [
    ("after_nonce_db_before_witness", ("candidate_consumptions_not_witnessed",)),
    ("after_witness_before_nonce_db", ("witnessed_consumptions_missing_from_candidate",)),
    ("after_key_db_before_witness", ("candidate_key_epoch_ahead_of_witness",
                                     "candidate_verifier_identity_differs_from_witness",
                                     "candidate_revocations_differ_from_witness")),
    ("after_witness_before_key_db", ("candidate_key_epoch_behind_witness",
                                     "candidate_verifier_identity_differs_from_witness",
                                     "candidate_revocations_differ_from_witness")),
])
def test_each_independent_crash_cutpoint_blocks_automatic_resume(
    laboratory, stage, issues,
):
    lab = laboratory
    if stage == "after_nonce_db_before_witness":
        mutate_nonce(lab)
        index = 0
    elif stage == "after_witness_before_nonce_db":
        index = 1
    elif stage == "after_key_db_before_witness":
        mutate_nonce(lab)
        mutate_key(lab)
        index = 1
    elif stage == "after_witness_before_key_db":
        mutate_nonce(lab)
        index = 2
    else:
        raise AssertionError("Unrecognized fault cutpoint")
    result = recover(lab, index)
    assert set(issues).issubset(set(result.differences))
    assert not result.candidate_views_equal_signed_witness
    assert result.manual_reconciliation_required is True
    assert result.safe_to_resume_production is False
    assert result.authorizes_mutation is False


def test_both_candidate_dbs_and_signed_latest_head_can_match_without_trust(
    laboratory,
):
    mutate_nonce(laboratory)
    mutate_key(laboratory)
    result = recover(laboratory, 2)
    assert result.witness_sequence == 3
    assert result.witness_verifier_epoch == result.candidate_verifier_epoch == 5
    assert result.candidate_views_equal_signed_witness is True
    assert result.safe_to_resume_production is False
    assert result.production_deployment_authorized is False


def test_restored_old_candidate_files_detected_with_trusted_new_head(
    laboratory, tmp_path,
):
    lab = laboratory
    mutate_nonce(lab)
    mutate_key(lab)
    # Demonstrate database rollback by restoring exact earlier file contents.
    lab["key_db"].close()
    lab["op_db"].close()
    stale_k = tmp_path / "stale-k.sqlite"
    stale_o = tmp_path / "stale-o.sqlite"
    # Materialize initial snapshots in dedicated test databases; no physical I/O.
    conn = sqlite3.connect(stale_k)
    initialize_candidate_schema(conn)
    seed_candidate_for_test(
        conn, externally_pinned_initial_key=TrustedVerifierKey(lab["old"], 4),
    )
    conn.close()
    conn = sqlite3.connect(stale_o)
    initialize_operator_review_ledger(conn)
    conn.close()
    lab["key_db"] = sqlite3.connect(stale_k)
    lab["op_db"] = sqlite3.connect(stale_o)
    result = recover(lab, 2)
    assert "candidate_key_epoch_behind_witness" in result.differences
    assert "witnessed_consumptions_missing_from_candidate" in result.differences


def test_valid_old_signed_head_plus_restored_old_dbs_is_not_anti_rollback(
    laboratory, tmp_path,
):
    lab = laboratory
    mutate_nonce(lab)
    mutate_key(lab)
    # A caller who can also roll back the independent trusted latest digest
    # can make both the former SQL and formerly signed genesis look consistent.
    lab["key_db"].close()
    lab["op_db"].close()
    conn = sqlite3.connect(tmp_path/"k-old.db")
    initialize_candidate_schema(conn)
    seed_candidate_for_test(
        conn, externally_pinned_initial_key=TrustedVerifierKey(lab["old"], 4),
    )
    lab["key_db"] = conn
    conn = sqlite3.connect(tmp_path/"o-old.db")
    initialize_operator_review_ledger(conn)
    lab["op_db"] = conn
    result = recover(lab, 0)
    assert result.candidate_views_equal_signed_witness
    assert not result.independent_live_head_freshness_verified
    assert not result.safe_to_resume_production


def test_witness_head_mismatch_rejected_even_if_dbs_match(laboratory):
    with pytest.raises(ValueError, match="head"):
        recover(laboratory, 0,
                pinned_latest_head_sha256=laboratory["heads"][2])


def test_wrong_witness_signer_cannot_supply_trusted_recovery_head(laboratory):
    _, attacker = ephemeral()
    with pytest.raises(ValueError, match="signature"):
        recover(laboratory, 0, pinned_witness_public_key=attacker)


def test_other_device_challenge_row_denied_even_with_valid_witness(
    laboratory,
):
    mutate_nonce(laboratory, device="another-board")
    with pytest.raises(ValueError, match="cross-device"):
        recover(laboratory, 0)


def test_corrupt_key_fingerprint_denied_without_modifying_database(laboratory):
    lab = laboratory
    lab["key_db"].execute(
        "UPDATE candidate_verifier_state SET fingerprint=? WHERE singleton=1",
        ("f"*64,),
    )
    lab["key_db"].commit()
    with pytest.raises(ValueError, match="Corrupt"):
        recover(lab, 0)
    assert not lab["key_db"].in_transaction
    assert not lab["op_db"].in_transaction


def test_both_input_connections_must_be_idle_and_separate(laboratory):
    lab = laboratory
    with pytest.raises(ValueError, match="Two separate"):
        recover(lab, 0, candidate_operator_db=lab["key_db"])
    lab["key_db"].execute("BEGIN")
    try:
        with pytest.raises(ValueError, match="idle"):
            recover(lab, 0)
    finally:
        lab["key_db"].rollback()


def test_absent_candidate_table_fails_closed(laboratory):
    conn = laboratory["op_db"]
    conn.execute("DROP TABLE candidate_operator_challenges")
    conn.commit()
    with pytest.raises(ValueError, match="missing/corrupt"):
        recover(laboratory, 0)
    assert not conn.in_transaction


def test_malformed_candidate_nonce_history_is_not_silently_ignored(laboratory):
    lab = laboratory
    mutate_nonce(lab, consumed=False)
    lab["op_db"].execute(
        "UPDATE candidate_operator_challenges SET issued_unix=-2, expires_unix=-1"
    )
    lab["op_db"].commit()
    with pytest.raises(ValueError, match="Invalid"):
        recover(lab, 0)


def test_source_module_never_writes_repairs_signs_or_promotes():
    import core.selfdev_recovery_consistency as module
    source = Path(module.__file__).read_text()
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "INSERT INTO",
        "UPDATE ", "DELETE FROM", "os.replace(", "os.chown(",
        "SelfDevPromotionManager", "systemctl", "subprocess.",
    ):
        assert forbidden not in source
    assert "production_deployment_authorized: bool = False" in source
    assert "safe_to_resume_production: bool = False" in source
    assert "external_durable_commit_verified: bool = False" in source
