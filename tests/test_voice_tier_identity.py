"""Synthetic, no-I/O tests for factory-bound independent STT evidence."""
import pytest

from core.voice_tier_identity import TrustedSTTBindings


class STT:
    def transcribe(self, audio):
        return {"text": "unused"}


def records():
    p, c, w = STT(), STT(), STT()
    models = [
        {"key": "p", "provider": p, "family": "parakeet",
         "sha256": "a" * 64},
        {"key": "c", "provider": c, "family": "canary",
         "sha256": "b" * 64},
        {"key": "w", "provider": w, "family": "whisper",
         "sha256": "c" * 64},
    ]
    return models, (p, c, w)


def test_one_registered_provider_can_answer_low_risk():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [(p, "Vad är klockan?")])["accepted"]


def test_medium_requires_distinct_model_families():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("medium", [
        (p, "Anslut till Razer"), (c, "Anslut till Razer"),
    ])["accepted"]


def test_critical_three_families_are_verified():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    out = binder.verify("critical", [
        (p, "Radera rapport.txt"),
        (c, "Radera rapport.txt"),
        (w, "Radera rapport.txt"),
    ])
    assert out["accepted"] is True
    assert out["support"] == 3


def test_unregistered_provider_cannot_claim_identity_from_text():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [
        (STT(), "hej")
    ])["reason"] == "untrusted-provider"


def test_duplicate_provider_vote_rejected():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("medium", [
        (p, "Anslut"), (p, "Anslut")
    ])["reason"] == "duplicate_or_invalid_model"


def test_same_family_cannot_register_as_two_independent_providers():
    entries, (p, c, w) = records()
    entries[1]["family"] = "parakeet"
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


def test_same_object_cannot_register_twice():
    entries, (p, c, w) = records()
    entries[1]["provider"] = p
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


@pytest.mark.parametrize("sha", [
    "not-a-hash", "a" * 63, "a" * 65, "A" * 64, "", None,
])
def test_unpinned_or_malformed_weight_digest_rejected(sha):
    entries, _ = records()
    entries[0]["sha256"] = sha
    with pytest.raises(ValueError):
        TrustedSTTBindings(entries)


def test_no_string_cast_of_model_supplied_dict_or_metadata():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("low", [
        (p, {"text": "hej", "model_key": "w"}),
    ])["reason"] == "invalid-transcript"


def test_negation_disagreement_is_not_relabelled_as_consensus():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("critical", [
        (p, "Radera rapport.txt"),
        (c, "Radera rapport.txt"),
        (w, "Radera inte rapport.txt"),
    ])["accepted"] is False


def test_critical_must_have_three_observed_sources_even_if_two_agree():
    entries, (p, c, w) = records()
    binder = TrustedSTTBindings(entries)
    assert binder.verify("critical", [
        (p, "Radera rapport.txt"), (c, "Radera rapport.txt")
    ])["reason"] == "missing_or_extra_votes"
