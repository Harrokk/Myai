"""Adversarial tests for offline witness checkpoints; all keys are disposable."""
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from core.selfdev_signed_witness_checkpoint import (
    DOMAIN, ISSUER, AUDIENCE, PURPOSE, WitnessSnapshot,
    canonical_witness_checkpoint, inspect_witness_chain,
)

DEVICE = "synthetic_ventuno_1"
NOW = 1_800_000_000


def make_key():
    secret = Ed25519PrivateKey.generate()
    public = secret.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)
    return secret, public


def state(public, *, sequence=1, epoch=4, previous="0"*64,
          retired=(), consumed=(), at=NOW, **changes):
    obj = {
        "version": 1, "issuer": ISSUER, "purpose": PURPOSE,
        "audience": AUDIENCE, "device_id": DEVICE,
        "sequence": sequence, "verifier_epoch": epoch,
        "verifier_public_key_hex": public.hex(),
        "verifier_fingerprint": hashlib.sha256(public).hexdigest(),
        "retired_verifier_fingerprints": sorted(retired),
        "consumed_operator_nonces": sorted(consumed),
        "previous_checkpoint_sha256": previous,
        "recorded_unix": at,
    }
    obj.update(changes)
    return obj


def sign(secret, statement):
    signed = canonical_witness_checkpoint(statement)
    wire = json.dumps({
        "statement": statement,
        "signature": secret.sign(signed).hex(),
    }, sort_keys=True, separators=(",", ":")).encode()
    return wire, hashlib.sha256(signed).hexdigest()


def inspect(wires, public, genesis, head, **kwargs):
    args = dict(
        trusted_witness_public_key=public,
        independently_pinned_genesis_sha256=genesis,
        independently_pinned_latest_sha256=head,
        expected_device_id=DEVICE,
    )
    args.update(kwargs)
    return inspect_witness_chain(wires, **args)


def sample_history():
    witness_secret, witness_public = make_key()
    _, previous_key = make_key()
    _, current_key = make_key()
    before = state(previous_key)
    genesis_wire, genesis_digest = sign(witness_secret, before)
    second = state(
        previous_key, sequence=2, previous=genesis_digest,
        consumed=("a"*32,), at=NOW+1,
    )
    second_wire, second_digest = sign(witness_secret, second)
    third = state(
        current_key, sequence=3, epoch=5, previous=second_digest,
        retired=(hashlib.sha256(previous_key).hexdigest(),),
        consumed=("a"*32, "b"*32), at=NOW+2,
    )
    third_wire, third_digest = sign(witness_secret, third)
    return (witness_secret, witness_public,
            [genesis_wire, second_wire, third_wire],
            [genesis_digest, second_digest, third_digest],
            previous_key, current_key)


def test_complete_signed_chain_retirement_nonce_and_frozen_no_go_receipt():
    _, public, wires, hashes, old, current = sample_history()
    result = inspect(wires, public, hashes[0], hashes[-1])
    assert isinstance(result, WitnessSnapshot)
    assert result.sequence == 3 and result.verifier_epoch == 5
    assert result.verifier_public_key == current
    assert result.checkpoint_sha256 == hashes[-1]
    assert result.retired_verifier_fingerprints == frozenset({
        hashlib.sha256(old).hexdigest(),
    })
    assert result.consumed_operator_nonces == frozenset({"a"*32,"b"*32})
    assert result.signature_verified is True
    assert result.independently_pinned_head_matched is True
    assert result.actual_external_witness_storage_verified is False
    assert result.witness_signing_key_provisioned is False
    assert result.power_loss_or_restore_resistance_verified is False
    assert result.external_head_advancement_performed is False
    assert result.human_approval_verified is False
    assert result.authorizes_mutation is False
    assert result.production_deployment_authorized is False
    with pytest.raises(FrozenInstanceError):
        result.production_deployment_authorized = True


def test_key_order_does_not_change_canonical_signing_bytes():
    _, public = make_key()
    item = state(public)
    assert canonical_witness_checkpoint(item).startswith(DOMAIN)
    assert canonical_witness_checkpoint(item) == canonical_witness_checkpoint(
        dict(reversed(list(item.items())))
    )


@pytest.mark.parametrize("patch", [
    {"version": True}, {"version": 2}, {"issuer":"runtime"},
    {"purpose":"promote"}, {"audience":"updater-production"},
    {"device_id":"../other"}, {"device_id":""},
    {"sequence":True}, {"sequence":0}, {"sequence":2**31},
    {"verifier_epoch":True}, {"verifier_epoch":0},
    {"recorded_unix":True}, {"recorded_unix":-1},
    {"verifier_public_key_hex":"0"*63},
    {"verifier_fingerprint":"f"*64},
    {"previous_checkpoint_sha256":"A"*64},
    {"retired_verifier_fingerprints":["A"*64]},
    {"retired_verifier_fingerprints":["a"*64,"a"*64]},
    {"consumed_operator_nonces":["A"*32]},
    {"consumed_operator_nonces":["b"*32,"a"*32]},
    {"consumed_operator_nonces":["a"*32,"a"*32]},
    {"consumed_operator_nonces":["a"*32]*257},
    {"retired_verifier_fingerprints":["a"*64]*257},
])
def test_wrong_or_ambiguous_checkpoint_cannot_be_signed(patch):
    _, public = make_key()
    with pytest.raises(ValueError):
        canonical_witness_checkpoint(state(public, **patch))


@pytest.mark.parametrize("extra", [
    "trusted_witness_key", "private_key", "approved", "production_promotion",
    "new_epoch_override", "signing_command", "operator_authorized",
])
def test_unknown_fields_forbidden(extra):
    _, public = make_key()
    with pytest.raises(ValueError):
        canonical_witness_checkpoint(state(public, **{extra:True}))


def test_old_signed_head_is_rejected_when_independent_head_has_advanced():
    _, pub, wires, hashes, *_ = sample_history()
    with pytest.raises(ValueError, match="head"):
        inspect(wires[:2], pub, hashes[0], hashes[-1])
    # A *stale externally pinned latest digest* defeats the rollback check.
    # This is intentional evidence that local signatures alone are insufficient.
    outdated = inspect(wires[:2], pub, hashes[0], hashes[1])
    assert outdated.verifier_epoch == 4
    assert outdated.power_loss_or_restore_resistance_verified is False


def test_only_separately_pinned_witness_public_key_is_accepted():
    _, _, wires, hashes, *_ = sample_history()
    _, attacker_key = make_key()
    with pytest.raises(ValueError, match="signature"):
        inspect(wires, attacker_key, hashes[0], hashes[-1])


def test_wrong_pinned_genesis_and_device_fail_closed():
    _, pub, wires, hashes, *_ = sample_history()
    with pytest.raises(ValueError, match="first"):
        inspect(wires, pub, "f"*64, hashes[-1])
    with pytest.raises(ValueError, match="device"):
        inspect(wires, pub, hashes[0], hashes[-1],
                expected_device_id="other_device")


@pytest.mark.parametrize("kind", [
    "tamper_body", "tamper_sig", "duplicate_top", "duplicate_nested",
    "nonfinite", "unknown_top", "oversized", "non_utf8",
])
def test_corrupt_signed_checkpoint_never_accepted(kind):
    _, pub, wires, hashes, *_ = sample_history()
    item = json.loads(wires[-1])
    if kind == "tamper_body":
        item["statement"]["recorded_unix"] += 1
    elif kind == "tamper_sig":
        item["signature"] = "0"*128
    elif kind == "unknown_top":
        item["operator_private_key"] = "x"
    elif kind == "duplicate_top":
        wires[-1] = wires[-1].replace(b'"signature":', b'"signature":"0","signature":',1)
    elif kind == "duplicate_nested":
        wires[-1] = wires[-1].replace(b'"verifier_epoch":5',
                                      b'"verifier_epoch":4,"verifier_epoch":5')
    elif kind == "nonfinite":
        wires[-1] = b'{"statement":NaN,"signature":"0"}'
    elif kind == "oversized":
        wires[-1] = b"z"*30001
    elif kind == "non_utf8":
        wires[-1] = b"\xff"
    if kind in ("tamper_body","tamper_sig","unknown_top"):
        wires[-1] = json.dumps(item).encode()
    with pytest.raises(ValueError):
        inspect(wires, pub, hashes[0], hashes[-1])


@pytest.mark.parametrize("bad", [
    [], (), "not-a-list", None, [b""], [b"{}"]*33,
])
def test_invalid_or_missing_chain_denied(bad):
    _, pub, _, hashes, *_ = sample_history()
    with pytest.raises(ValueError):
        inspect(bad,pub,hashes[0],hashes[-1])


@pytest.mark.parametrize("tampering", [
    "skipped_sequence", "wrong_parent", "epoch_jump",
    "epoch_regression", "changed_key_same_epoch", "missing_retirement",
    "extra_retirement", "nonce_rollback", "retirement_rollback",
    "fake_sequence_without_state_change", "time_rollback",
])
def test_monotonic_signed_witness_sequence_must_follow_exact_state_rules(tampering):
    witness, pub, wires, hashes, old, current = sample_history()
    # Construct a malicious but SIGNED third statement, so only semantics
    # of the independent history can catch the prohibited transition.
    altered = json.loads(wires[-1])["statement"]
    if tampering == "skipped_sequence":
        altered["sequence"] = 9
    elif tampering == "wrong_parent":
        altered["previous_checkpoint_sha256"] = "f"*64
    elif tampering == "epoch_jump":
        altered["verifier_epoch"] = 7
    elif tampering == "epoch_regression":
        altered["verifier_epoch"] = 3
    elif tampering == "changed_key_same_epoch":
        altered["verifier_epoch"] = 4
    elif tampering == "missing_retirement":
        altered["retired_verifier_fingerprints"] = []
    elif tampering == "extra_retirement":
        altered["retired_verifier_fingerprints"] = sorted([
            hashlib.sha256(old).hexdigest(), "c"*64,
        ])
    elif tampering == "nonce_rollback":
        altered["consumed_operator_nonces"] = []
    elif tampering == "retirement_rollback":
        # On 2nd step the old retired set is empty; construct a 4th step
        # that drops retirement from third.
        latest_wire, latest_digest = sign(witness, altered)
        fourth = state(
            current, sequence=4, epoch=5, previous=latest_digest,
            retired=(), consumed=("a"*32,"b"*32,"c"*32), at=NOW+3,
        )
        fourth_wire, fourth_digest = sign(witness, fourth)
        with pytest.raises(ValueError, match="history"):
            inspect(wires[:2] + [latest_wire, fourth_wire],
                    pub, hashes[0], fourth_digest)
        return
    elif tampering == "fake_sequence_without_state_change":
        altered["verifier_epoch"] = 4
        altered["verifier_public_key_hex"] = old.hex()
        altered["verifier_fingerprint"] = hashlib.sha256(old).hexdigest()
        altered["retired_verifier_fingerprints"] = []
        altered["consumed_operator_nonces"] = ["a"*32]
    elif tampering == "time_rollback":
        altered["recorded_unix"] = NOW-1
    else:
        raise AssertionError("Unknown test attack")
    signed, digest = sign(witness,altered)
    with pytest.raises(ValueError):
        inspect(wires[:2] + [signed], pub, hashes[0], digest)


def test_trust_anchor_mutation_and_no_production_promotion_in_module():
    import core.selfdev_signed_witness_checkpoint as module
    content = Path(module.__file__).read_text(encoding="utf-8")
    for forbidden in (
        "Ed25519PrivateKey", "sqlite3.connect(", "subprocess.",
        "systemctl", "SelfDevPromotionManager", "os.chown(",
        "os.chmod(", "save_verification(",
    ):
        assert forbidden not in content
    assert "production_deployment_authorized: bool = False" in content
    assert "actual_external_witness_storage_verified: bool = False" in content
