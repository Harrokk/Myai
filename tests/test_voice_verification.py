"""Synthetic tests for independent STT families and conservative consensus."""
import pytest

from core.voice_verification import verify_tiered_transcripts


MODELS = {
    "p": {"family": "parakeet", "revision": "sha256:pinned-a"},
    "c": {"family": "canary", "revision": "sha256:pinned-b"},
    "w": {"family": "whisper", "revision": "sha256:pinned-c"},
    "p2": {"family": "parakeet", "revision": "sha256:another-quant"},
}


def vote(key, text):
    return {"model_key": key, "text": text}


def check(tier, *votes, models=MODELS):
    return verify_tiered_transcripts(tier, list(votes), models)


def test_low_accepts_one_registered_model():
    result = check("low", vote("p", "Vad är klockan?"))
    assert result["accepted"] is True
    assert result["support"] == 1


def test_medium_requires_both_independent_exactly_agreeing():
    result = check(
        "medium",
        vote("p", "Anslut till headset 1"),
        vote("c", "Anslut till headset 1"),
    )
    assert result["accepted"] is True
    assert result["support"] == 2


@pytest.mark.parametrize("tier,example", [
    ("low", [vote("p", "hej"), vote("c", "hej")]),
    ("medium", [vote("p", "hej")]),
    ("critical", [vote("p", "radera"), vote("c", "radera")]),
])
def test_missing_or_extra_votes_fail(tier, example):
    assert check(tier, *example)["accepted"] is False


def test_medium_different_device_is_rejected():
    result = check(
        "medium", vote("p", "Anslut till headset A"),
        vote("c", "Anslut till headset B"),
    )
    assert result["accepted"] is False


def test_medium_connect_vs_disconnect_rejected():
    assert check(
        "medium", vote("p", "Anslut till headset"),
        vote("c", "Koppla från headset"),
    )["accepted"] is False


def test_same_family_different_quantization_is_not_independent():
    result = check(
        "medium", vote("p", "Anslut till headset"),
        vote("p2", "Anslut till headset"),
    )
    assert result["reason"] == "same_model_family"


def test_duplicate_model_cannot_vote_twice():
    assert check(
        "medium", vote("p", "Hej"), vote("p", "Hej"),
    )["reason"] == "duplicate_or_invalid_model"


def test_unknown_identity_blocks():
    assert check(
        "low", vote("unauthorized", "hej"),
    )["reason"] == "unknown_model"


def test_unpinned_identity_blocks():
    assert check(
        "low", vote("p", "hej"),
        models={"p": {"family": "parakeet", "revision": ""}},
    )["reason"] == "unverified_model_identity"


def test_critical_three_exact_independent_votes():
    result = check(
        "critical", vote("p", "Radera filen rapport.txt"),
        vote("c", "Radera filen rapport.txt"),
        vote("w", "Radera filen rapport.txt"),
    )
    assert result["accepted"] is True
    assert result["support"] == 3


def test_critical_two_exact_one_abstains():
    result = check(
        "critical", vote("p", "Radera filen rapport.txt"),
        vote("c", "Radera filen rapport.txt"),
        vote("w", ""),
    )
    assert result["accepted"] is True
    assert result["support"] == 2


@pytest.mark.parametrize("contradiction", [
    "Radera INTE filen rapport.txt",
    "Radera filen annan.txt",
    "Radera filen rapport2.txt",
    "Formatera disk C",
])
def test_critical_third_meaningful_disagreement_blocks(contradiction):
    result = check(
        "critical", vote("p", "Radera filen rapport.txt"),
        vote("c", "Radera filen rapport.txt"),
        vote("w", contradiction),
    )
    assert result["reason"] == "potentially_material_conflict"
    assert result["accepted"] is False


def test_critical_no_majority_blocks():
    result = check(
        "critical", vote("p", "radera a"),
        vote("c", "radera b"), vote("w", "radera c"),
    )
    assert result["reason"] == "no_exact_majority"


def test_critical_one_vote_plus_two_abstentions_blocks():
    result = check(
        "critical", vote("p", "radera a"),
        vote("c", ""), vote("w", ""),
    )
    assert result["reason"] == "insufficient_majority"


def test_medium_abstention_is_not_consensus():
    assert check(
        "medium", vote("p", "Anslut"), vote("c", ""),
    )["accepted"] is False


def test_invalid_non_string_transcript_fails():
    assert check(
        "low", {"model_key": "p", "text": {"tool": "delete"}},
    )["reason"] == "invalid_transcript"


def test_punctuation_and_case_do_not_create_false_conflict():
    result = check(
        "medium", vote("p", "Anslut till Hörlurarna!"),
        vote("c", "anslut till hörlurarna"),
    )
    assert result["accepted"] is True


def test_invalid_tier_denied():
    assert check("blocked", vote("p", "hej"))["reason"] == "invalid_tier"
