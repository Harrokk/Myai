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


def test_case_and_whitespace_do_not_create_false_conflict():
    result = check(
        "medium", vote("p", "  Anslut   till Hörlurarna "),
        vote("c", "anslut till hörlurarna"),
    )
    assert result["accepted"] is True


@pytest.mark.parametrize("first,second", [
    ("Anslut till enhet AA:BB", "Anslut till enhet AA BB"),
    ("Anslut till enhet AA-BB", "Anslut till enhet AA BB"),
    ("Öppna filen rapport.txt", "Öppna filen rapport txt"),
    ("Sätt volymen 1.5", "Sätt volymen 1 5"),
    ("Sätt volymen 1,5", "Sätt volymen 1 5"),
    ("Öppna /tmp/rapport", "Öppna tmp/rapport"),
    ("Kör fil C:\\Temp\\fil.txt", "Kör fil C Temp fil txt"),
    ("Visa status!", "Visa status"),
])
def test_distinct_punctuation_cannot_contribute_two_matching_votes(first, second):
    result = check("medium", vote("p", first), vote("c", second))
    assert result["accepted"] is False
    assert result["reason"] == "disagreement_or_abstention"


def test_critical_third_vote_differing_only_by_filename_dot_denies():
    result = check(
        "critical",
        vote("p", "Radera filen rapport.txt"),
        vote("c", "Radera filen rapport.txt"),
        vote("w", "Radera filen rapport txt"),
    )
    assert result["accepted"] is False
    assert result["reason"] == "potentially_material_conflict"


def test_invalid_tier_denied():
    assert check("blocked", vote("p", "hej"))["reason"] == "invalid_tier"


@pytest.mark.parametrize("first,second", [
    ("Radera filen rapport².txt", "Radera filen rapport2.txt"),
    ("Anslut till enhet ①", "Anslut till enhet 1"),
    ("Anslut till enhet ＡＢ:ＣＤ", "Anslut till enhet AB:CD"),
    ("Öppna filen version₅", "Öppna filen version5"),
])
def test_compatibility_unicode_distinctions_never_merge_medium_votes(first, second):
    # Under NFKC these pairs collapse to the same value. They can name
    # distinct files, devices or numerical identifiers; reject instead.
    decision = check("medium", vote("p", first), vote("c", second))
    assert decision["accepted"] is False
    assert decision["reason"] == "disagreement_or_abstention"


@pytest.mark.parametrize("different", [
    "Radera filen rapport2.txt",
    "Radera filen rapport①.txt",
    "Radera filen rapport₅.txt",
])
def test_compatibility_unicode_change_from_third_critical_vote_denies(different):
    decision = check(
        "critical",
        vote("p", "Radera filen rapport².txt"),
        vote("c", "Radera filen rapport².txt"),
        vote("w", different),
    )
    assert decision["accepted"] is False
    assert decision["reason"] == "potentially_material_conflict"


def test_nfc_allows_only_canonical_accent_composition():
    decision = check(
        "medium",
        vote("p", "Anslut till enhet Blå"),
        vote("c", "Anslut till enhet Bla\u030a"),
    )
    assert decision["accepted"] is True
    assert decision["text"] == "anslut till enhet blå"
