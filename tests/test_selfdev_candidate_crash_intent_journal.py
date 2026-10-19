"""Disposable SQLite + genuine signed-witness fault injection; no live services."""
from dataclasses import FrozenInstanceError
import concurrent.futures
import hashlib
import json
from pathlib import Path
import shutil
import sqlite3
import threading

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_candidate_crash_intent_journal import (
    STAGES, CandidateIntentSnapshot, IntentRecoveryReview,
    initialize_candidate_intent_journal, create_candidate_intent,
    record_candidate_milestone, read_candidate_intent,
    inspect_candidate_intent_recovery,
)
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

DEVICE = "disposable_witness_test"
NONCE = "a" * 32
NOW = 1_800_000_000
INTENT_ID = "test_intent_0001"
ROTATION_DIGEST = "b" * 64


def pair():
    secret = Ed25519PrivateKey.generate()
    public = secret.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return secret, public


def checkpoint(secret, key, epoch, sequence, previous, revoked=(), consumed=()):
    body = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "device_id": DEVICE,
        "sequence": sequence, "verifier_epoch": epoch,
        "verifier_public_key_hex": key.hex(),
        "verifier_fingerprint": hashlib.sha256(key).hexdigest(),
        "retired_verifier_fingerprints": sorted(revoked),
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": previous,
        "recorded_unix": NOW + sequence,
    }
    signed = canonical_witness_checkpoint(body)
    return json.dumps({
        "statement": body, "signature": secret.sign(signed).hex(),
    }, sort_keys=True, separators=(",", ":")).encode(), hashlib.sha256(signed).hexdigest()


@pytest.fixture
def lab(tmp_path):
    signing_key, signing_pub = pair()
    _, old_key = pair()
    _, new_key = pair()
    genesis, genesis_head = checkpoint(signing_key, old_key, 4, 1, "0"*64)
    middle, middle_head = checkpoint(
        signing_key, old_key, 4, 2, genesis_head, consumed=(NONCE,),
    )
    final, final_head = checkpoint(
        signing_key, new_key, 5, 3, middle_head,
        revoked=(hashlib.sha256(old_key).hexdigest(),), consumed=(NONCE,),
    )
    journal_path = tmp_path / "candidate-intents.sqlite"
    key_db = sqlite3.connect(tmp_path / "candidate-keys.sqlite", timeout=5)
    operator_db = sqlite3.connect(tmp_path / "candidate-operators.sqlite", timeout=5)
    journal = sqlite3.connect(journal_path, timeout=5)
    initialize_candidate_schema(key_db)
    initialize_operator_review_ledger(operator_db)
    initialize_candidate_intent_journal(journal)
    seed_candidate_for_test(
        key_db, externally_pinned_initial_key=TrustedVerifierKey(old_key, 4),
    )
    snapshot = create_candidate_intent(
        journal, intent_id=INTENT_ID, device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION_DIGEST,
        expected_operator_witness_head=middle_head,
        expected_final_witness_head=final_head,
        created_unix=NOW,
    )
    l = {
        "journal": journal, "journal_path": journal_path,
        "keys": key_db, "operator": operator_db, "old": old_key,
        "new": new_key, "witness_pub": signing_pub,
        "wires": (genesis, middle, final),
        "heads": (genesis_head, middle_head, final_head),
        "created": snapshot,
    }
    yield l
    for conn in (l["journal"], l["keys"], l["operator"]):
        if conn:
            conn.close()


def stage(l, *milestones):
    for phase in milestones:
        index = STAGES.index(phase)
        recorded_head = (l["heads"][1] if index == 2 else
                         l["heads"][2] if index == 4 else "0"*64)
        record_candidate_milestone(
            l["journal"], intent_id=INTENT_ID,
            next_stage=phase, observed_witness_head=recorded_head,
        )


def use_operator_nonce(l):
    db = l["operator"]
    db.execute(
        """INSERT INTO candidate_operator_challenges
           (challenge,device_id,old_epoch,old_fingerprint,new_fingerprint,
            rotation_sha256,operator_fingerprint,issued_unix,expires_unix,consumed_unix)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (NONCE, DEVICE, 4, hashlib.sha256(l["old"]).hexdigest(),
         hashlib.sha256(l["new"]).hexdigest(), ROTATION_DIGEST, "c"*64,
         NOW, NOW+60, NOW+1),
    )
    db.commit()


def rotate_key_candidate(l):
    db = l["keys"]
    db.execute(
        """UPDATE candidate_verifier_state
           SET epoch=5, public_key=?,fingerprint=? WHERE singleton=1""",
        (l["new"], hashlib.sha256(l["new"]).hexdigest()),
    )
    db.execute(
        "INSERT INTO candidate_verifier_revoked VALUES (?,5)",
        (hashlib.sha256(l["old"]).hexdigest(),),
    )
    db.commit()


def recover(l, witness_index):
    return inspect_recovery_consistency(
        candidate_key_db=l["keys"], candidate_operator_db=l["operator"],
        witness_envelopes=l["wires"][:witness_index+1],
        pinned_witness_public_key=l["witness_pub"],
        pinned_genesis_sha256=l["heads"][0],
        pinned_latest_head_sha256=l["heads"][witness_index],
        expected_device_id=DEVICE,
    )


def inspect(l, witness_index):
    return inspect_candidate_intent_recovery(
        l["journal"], intent_id=INTENT_ID,
        verified_recovery_inspection=recover(l, witness_index),
    )


def test_created_intent_is_frozen_and_non_authorizing(lab):
    snap = lab["created"]
    assert isinstance(snap, CandidateIntentSnapshot)
    assert snap.recorded_stage == STAGES[0]
    assert snap.recorded_stage_index == 0
    assert snap.journal_chain_consistent
    assert not snap.actual_external_milestones_verified
    assert not snap.witness_freshness_independently_verified
    assert not snap.crash_recovery_automatically_permitted
    assert not snap.authorizes_mutation
    assert not snap.production_deployment_authorized
    with pytest.raises(FrozenInstanceError):
        snap.production_deployment_authorized = True


def test_all_ordered_journal_milestones_are_explicit_claims_only(lab):
    for expected_index, phase in enumerate(STAGES[1:], start=1):
        stage(lab, phase)
        entry = read_candidate_intent(lab["journal"], intent_id=INTENT_ID)
        assert entry.recorded_stage_index == expected_index
        assert entry.recorded_stage == phase
        assert entry.journal_chain_consistent
        assert not entry.actual_external_milestones_verified
        assert not entry.authorizes_mutation
    with pytest.raises(ValueError, match="Reordered"):
        stage(lab, STAGES[-1])


@pytest.mark.parametrize("next_stage", [
    STAGES[0], STAGES[2], STAGES[3], "promote", "runtime", True, "", None,
])
def test_journal_rejects_skipped_forged_or_unknown_stage(lab, next_stage):
    with pytest.raises(ValueError):
        record_candidate_milestone(
            lab["journal"], intent_id=INTENT_ID, next_stage=next_stage,
        )
    assert read_candidate_intent(
        lab["journal"], intent_id=INTENT_ID,
    ).recorded_stage == "prepared"
    assert not lab["journal"].in_transaction


def test_journal_refuses_forged_witness_digest_and_rolls_back(lab):
    stage(lab, STAGES[1])
    with pytest.raises(ValueError, match="planned"):
        record_candidate_milestone(
            lab["journal"], intent_id=INTENT_ID, next_stage=STAGES[2],
            observed_witness_head="f"*64,
        )
    assert read_candidate_intent(lab["journal"], intent_id=INTENT_ID).recorded_stage == STAGES[1]
    assert not lab["journal"].in_transaction


@pytest.mark.parametrize("patch", [
    {"intent_id": "../other"},
    {"device_id": "target/other"},
    {"operator_nonce": "A"*32},
    {"expected_old_epoch": True},
    {"expected_new_epoch": 7},
    {"created_unix": True},
    {"rotation_sha256": "0"},
    {"expected_operator_witness_head": "Z"*64},
    {"expected_final_witness_head": "0"},
])
def test_bad_intent_context_fails_before_any_sql_write(tmp_path, patch):
    db = sqlite3.connect(tmp_path / "bad-intent.sqlite")
    initialize_candidate_intent_journal(db)
    params = dict(
        intent_id="test", device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION_DIGEST,
        expected_operator_witness_head="c"*64,
        expected_final_witness_head="d"*64, created_unix=NOW,
    )
    params.update(patch)
    try:
        with pytest.raises(ValueError):
            create_candidate_intent(db, **params)
        assert db.execute("SELECT count(*) FROM candidate_crash_intents").fetchone()[0] == 0
    finally:
        db.close()


def test_duplicate_intent_or_operator_nonce_refused(lab):
    params = dict(
        intent_id=INTENT_ID, device_id=DEVICE, operator_nonce=NONCE,
        expected_old_epoch=4, expected_new_epoch=5,
        rotation_sha256=ROTATION_DIGEST,
        expected_operator_witness_head=lab["heads"][1],
        expected_final_witness_head=lab["heads"][2], created_unix=NOW,
    )
    with pytest.raises(sqlite3.IntegrityError):
        create_candidate_intent(lab["journal"], **params)
    params["intent_id"] = "different_intent"
    with pytest.raises(sqlite3.IntegrityError):
        create_candidate_intent(lab["journal"], **params)
    assert not lab["journal"].in_transaction


@pytest.mark.parametrize("tamper", [
    "event_digest", "previous_event_digest", "stage", "stage_index",
    "operator_nonce", "epoch", "head",
])
def test_tampered_journal_rows_cannot_appear_consistent(lab, tamper):
    db = lab["journal"]
    changes = {
        "event_digest": ("UPDATE candidate_crash_events SET event_digest=?", ("f"*64,)),
        "previous_event_digest": (
            "UPDATE candidate_crash_events SET previous_event_digest=?", ("f"*64,)
        ),
        "stage": ("UPDATE candidate_crash_events SET stage=?", ("promote",)),
        "stage_index": ("UPDATE candidate_crash_events SET stage_index=?", (3,)),
        "operator_nonce": (
            "UPDATE candidate_crash_intents SET operator_nonce=?", ("x"*32,)
        ),
        "epoch": ("UPDATE candidate_crash_intents SET expected_new_epoch=?", (7,)),
        "head": (
            "UPDATE candidate_crash_intents SET expected_final_witness_head=?",
            (lab["heads"][1],),
        ),
    }
    sql, values = changes[tamper]
    db.execute(sql, values)
    db.commit()
    with pytest.raises(ValueError):
        read_candidate_intent(db, intent_id=INTENT_ID)


def test_sqlite_journal_after_reopen_remembers_last_claim(lab):
    stage(lab, STAGES[1], STAGES[2])
    lab["journal"].close()
    lab["journal"] = sqlite3.connect(lab["journal_path"])
    result = read_candidate_intent(lab["journal"], intent_id=INTENT_ID)
    assert result.recorded_stage == STAGES[2]
    assert result.observed_witness_head == lab["heads"][1]


def test_same_candidate_step_cannot_both_commit_concurrently(lab):
    db = lab["journal"]
    db.close()
    lab["journal"] = None
    barrier = threading.Barrier(2)
    def worker():
        connection = sqlite3.connect(lab["journal_path"], timeout=4)
        try:
            barrier.wait(timeout=3)
            try:
                record_candidate_milestone(
                    connection, intent_id=INTENT_ID, next_stage=STAGES[1],
                )
                return "recorded"
            except ValueError:
                return "denied"
        finally:
            connection.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        statuses = [future.result(timeout=8) for future in (
            pool.submit(worker), pool.submit(worker)
        )]
    assert sorted(statuses) == ["denied", "recorded"]
    lab["journal"] = sqlite3.connect(lab["journal_path"])


@pytest.mark.parametrize("stage_name,witness_index,changes,expected_problem", [
    ("prepared", 0, (), None),
    ("operator_db_recorded", 0, ("nonce",), "candidate_consumptions_not_witnessed"),
    ("operator_witness_recorded", 1, ("nonce",), None),
    ("key_db_recorded", 1, ("nonce","key"), "candidate_key_epoch_ahead_of_witness"),
    ("key_witness_recorded", 2, ("nonce","key"), None),
])
def test_fault_cutpoint_recovery_never_authorizes_continuation(
    lab, stage_name, witness_index, changes, expected_problem,
):
    index = STAGES.index(stage_name)
    stage(lab, *STAGES[1:index+1])
    if "nonce" in changes:
        use_operator_nonce(lab)
    if "key" in changes:
        rotate_key_candidate(lab)
    report = inspect(lab, witness_index)
    assert isinstance(report, IntentRecoveryReview)
    assert report.recorded_stage == stage_name
    assert report.manual_reconciliation_required is True
    assert report.automatic_resume_permitted is False
    assert report.journal_stage_is_externally_proven is False
    assert report.external_head_freshness_verified is False
    assert report.authorizes_mutation is False
    assert report.production_deployment_authorized is False
    if expected_problem:
        assert expected_problem in report.observed_recovery_differences
    else:
        assert report.observed_recovery_differences == ()


def test_witness_claim_mismatch_cannot_be_hidden_by_a_valid_old_head(lab):
    stage(lab, STAGES[1], STAGES[2])
    # A stage claim is *not* a witness proof. Here the independent trusted
    # witness still has only a genesis head and no nonce has been used.
    result = inspect(lab, 0)
    assert "journal_claimed_witness_milestone_not_observed" in (
        result.observed_recovery_differences
    )
    assert not result.automatic_resume_permitted


def test_stale_journal_and_stale_external_head_cannot_be_called_safe(lab, tmp_path):
    lab["journal"].close()
    old_copy = tmp_path / "rolled_back_journal.sqlite"
    shutil.copyfile(lab["journal_path"], old_copy)
    lab["journal"] = sqlite3.connect(old_copy)
    report = inspect(lab, 0)
    assert report.recorded_stage == "prepared"
    assert report.observed_recovery_differences == ()
    assert not report.external_head_freshness_verified
    assert not report.automatic_resume_permitted


def test_unknown_signed_witness_or_other_device_is_never_applied_to_intent(lab):
    bad = RecoveryInspection(
        device_id="different_device", witness_head_sha256=lab["heads"][0],
        witness_sequence=1, witness_verifier_epoch=4,
        candidate_verifier_epoch=4, differences=(),
        candidate_views_equal_signed_witness=True,
        manual_reconciliation_required=False,
    )
    with pytest.raises(ValueError, match="device"):
        inspect_candidate_intent_recovery(
            lab["journal"], intent_id=INTENT_ID,
            verified_recovery_inspection=bad,
        )
    with pytest.raises(ValueError):
        inspect_candidate_intent_recovery(
            lab["journal"], intent_id=INTENT_ID,
            verified_recovery_inspection={"production_deployment_authorized": True},
        )


def test_journal_does_not_sign_control_external_storage_or_production():
    import core.selfdev_candidate_crash_intent_journal as journal
    source = Path(journal.__file__).read_text(encoding="utf-8")
    for fragment in (
        "Ed25519PrivateKey", "sqlite3.connect(", "systemctl",
        "SelfDevPromotionManager", "subprocess.", "os.chmod(", "os.chown(",
        "fsync(", "production_deployment_authorized: bool = True",
    ):
        assert fragment not in source
    assert "automatic_resume_permitted: bool = False" in source
    assert "authorizes_mutation: bool = False" in source
