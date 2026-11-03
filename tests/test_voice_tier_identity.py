"""Synthetic, no-I/O tests for factory-bound independent STT evidence."""
import hashlib
import pytest

from core.voice_model_provenance import verify_stt_model_files

from core.voice_tier_identity import TrustedSTTBindings


class STT:
    def __init__(self, model_name):
        self.model_name = model_name

    def transcribe(self, audio):
        return {"text": "unused"}


def records(tmp_path):
    models = []
    providers = []
    for key, family in (("p", "parakeet"), ("c", "canary"),
                        ("w", "whisper")):
        root = tmp_path / family
        root.mkdir()
        data = ("synthetic " + family).encode("utf-8")
        path = root / "weights.bin"
        path.write_bytes(data)
        path.chmod(0o444)
        root.chmod(0o555)
        bundle = verify_stt_model_files(
            root, family=family,
            expected_sha256={"weights.bin": hashlib.sha256(data).hexdigest()},
        )
        provider = STT(bundle.root)
        providers.append(provider)
        models.append({"key": key, "provider": provider, "bundle": bundle})
    return models, tuple(providers)


def test_one_registered_provider_can_answer_low_risk(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [(p, "Vad är klockan?")])["accepted"]


def test_medium_requires_distinct_model_families(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("medium", [
        (p, "Anslut till Razer"), (c, "Anslut till Razer"),
    ])["accepted"]


def test_critical_three_families_are_verified(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    out = binder.verify("critical", [
        (p, "Radera rapport.txt"),
        (c, "Radera rapport.txt"),
        (w, "Radera rapport.txt"),
    ])
    assert out["accepted"] is True
    assert out["support"] == 3


def test_unregistered_provider_cannot_claim_identity_from_text(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [
        (STT("unregistered"), "hej")
    ])["reason"] == "untrusted-provider"


def test_duplicate_provider_vote_rejected(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("medium", [
        (p, "Anslut"), (p, "Anslut")
    ])["reason"] == "duplicate_or_invalid_model"


def test_same_family_cannot_register_as_two_independent_providers(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    entries[1]["family"] = "parakeet"
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


def test_same_object_cannot_register_twice(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    entries[1]["provider"] = p
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


@pytest.mark.parametrize("sha", [
    "not-a-hash", "a" * 63, "a" * 65, "A" * 64, "", None,
])
def test_unpinned_or_malformed_weight_digest_rejected(tmp_path, sha):
    entries, _ = records(tmp_path)
    entries[0]["sha256"] = sha
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


def test_no_string_cast_of_model_supplied_dict_or_metadata(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [
        (p, {"text": "hej", "model_key": "w"}),
    ])["reason"] == "invalid-transcript"


def test_negation_disagreement_is_not_relabelled_as_consensus(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("critical", [
        (p, "Radera rapport.txt"),
        (c, "Radera rapport.txt"),
        (w, "Radera inte rapport.txt"),
    ])["accepted"] is False


def test_critical_must_have_three_observed_sources_even_if_two_agree(tmp_path):
    entries, (p, c, w) = records(tmp_path)
    binder = TrustedSTTBindings(entries)
    assert binder.verify("critical", [
        (p, "Radera rapport.txt"), (c, "Radera rapport.txt")
    ])["reason"] == "missing_or_extra_votes"
