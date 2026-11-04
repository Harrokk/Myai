"""Hosted-only unit contracts for three distinct pinned ASR model families."""
import pytest

from scripts.ci_three_family_human_swedish_trial import (
    EXPECTED_FAMILIES, NATIVE_PROFILES, _PROFILE_TO_KEY,
    _summarize_metrics,
)
from core.voice_candidate_hosted_releases import hosted_model_release
from core.voice_verification import verify_tiered_transcripts


def test_three_distinct_model_families_never_use_two_whisper_variants():
    assert EXPECTED_FAMILIES == {"canary", "parakeet", "whisper"}
    assert set(_PROFILE_TO_KEY) == EXPECTED_FAMILIES
    assert len(set(_PROFILE_TO_KEY.values())) == 3
    assert NATIVE_PROFILES == ("canary-1b-v2-q8", "whisper-small-q5_1")
    assert hosted_model_release(NATIVE_PROFILES[0]).family == "canary"
    assert hosted_model_release(NATIVE_PROFILES[1]).family == "whisper"


def test_aggregated_wer_from_actual_edits_not_mean_of_utterance_rates():
    observations = [
        {"errors": 1, "words": 2, "text": "hej", "latency": 1.0},
        {"errors": 1, "words": 8, "text": "", "latency": 9.0},
    ]
    result = _summarize_metrics("parakeet", observations, 2048)
    assert result["samples"] == 2
    assert result["word_edits"] == 2
    assert result["reference_words"] == 10
    assert result["corpus_wer"] == 0.2
    assert result["empty_transcripts"] == 1
    assert result["p95_wall_seconds"] == 9.0
    assert result["sampled_python_and_descendant_peak_rss_mib"] == 2.0


def test_three_identical_model_family_votes_are_not_independent():
    keys = {"p": {"family": "whisper", "revision": "one"},
            "c": {"family": "whisper", "revision": "two"},
            "w": {"family": "whisper", "revision": "three"}}
    votes = [{"model_key": k, "text": "Kontrollera RAM"}
             for k in ("p", "c", "w")]
    result = verify_tiered_transcripts("critical", votes, keys)
    assert result["accepted"] is False
    assert result["reason"] == "same_model_family"


@pytest.mark.parametrize("variant", ["fil.txt", "fil txt"])
def test_punctuation_differences_never_become_model_family_agreement(variant):
    models = {
        "p": {"family": "parakeet", "revision": "pinned-p"},
        "c": {"family": "canary", "revision": "pinned-c"},
        "w": {"family": "whisper", "revision": "pinned-w"},
    }
    votes = [
        {"model_key": "p", "text": "Radera " + variant},
        {"model_key": "c", "text": "Radera fil.txt"},
        {"model_key": "w", "text": "Radera fil txt"},
    ]
    result = verify_tiered_transcripts("critical", votes, models)
    assert result["accepted"] is False

from scripts.ci_three_family_human_swedish_trial import (
    THREE_FAMILY_SAMPLES, paired_exact_agreement,
)


def test_paired_wrong_agreement_is_counted_not_approved():
    assert THREE_FAMILY_SAMPLES == 36
    obs = {
        "parakeet": [{"text": "rapport 2"}, {"text": "stäng av"}],
        "canary": [{"text": "Rapport 2"}, {"text": "stäng av"}],
        "whisper": [{"text": "rapport 2"}, {"text": "stoppa"}],
    }
    summary = paired_exact_agreement(obs, ["rapport 2", "stäng inte av"])
    assert summary["three_same_correct"] == 1
    assert summary["three_same_wrong"] == 0
    a = summary["pairwise_counts"]["parakeet_vs_canary"]
    assert a == {
        "exact_agreement": 2,
        "correct_exact_agreement": 1,
        "same_wrong_agreement": 1,
        "both_differ_from_reference": 1,
    }
    assert summary["wrong_agreement_is_never_authorization"] is True
    assert "stäng av" not in str(summary)


def test_three_identical_wrong_utterances_are_detected_as_wrong():
    obs = {f: [{"text": "radera fil.txt"}]
           for f in ("parakeet", "canary", "whisper")}
    summary = paired_exact_agreement(obs, ["radera inte fil.txt"])
    assert summary["three_same_wrong"] == 1
    assert summary["three_same_correct"] == 0


@pytest.mark.parametrize("missing", ["parakeet", "canary", "whisper"])
def test_paired_results_require_exactly_three_families(missing):
    obs = {f: [{"text": "hej"}] for f in ("parakeet", "canary", "whisper")
           if f != missing}
    with pytest.raises(ValueError):
        paired_exact_agreement(obs, ["hej"])


def test_paired_results_reject_different_number_of_samples():
    obs = {f: [{"text": "hej"}] for f in ("parakeet", "canary", "whisper")}
    obs["whisper"].append({"text": "hej"})
    with pytest.raises(ValueError):
        paired_exact_agreement(obs, ["hej"])


def test_word_level_accuracy_diagnostic_separately_accepts_punctuation_variants():
    observations = {
        "parakeet": [{"text": "Anslut till enhet AA BB"}],
        "canary": [{"text": "Anslut till enhet AA:BB"}],
        "whisper": [{"text": "Anslut till enhet AA BB"}],
    }
    result = paired_exact_agreement(observations, ["Anslut till enhet AA:BB"])
    # Never relax authorization: two different device IDs remain different.
    assert result["pairwise_counts"]["parakeet_vs_canary"]["exact_agreement"] == 0
    w = result["word_diagnostics_only"]
    assert w["pairwise_counts"]["parakeet_vs_canary"]["word_agreement"] == 1
    assert w["pairwise_counts"]["parakeet_vs_canary"]["word_correct_agreement"] == 1
    assert w["three_same_correct"] == 1
    assert w["not_for_authorization"] is True


def test_word_level_diagnostic_rejects_missing_negation():
    observations = {
        "parakeet": [{"text": "Radera inte filen"}],
        "canary": [{"text": "Radera filen"}],
        "whisper": [{"text": "Radera filen"}],
    }
    result = paired_exact_agreement(observations, ["Radera inte filen"])
    w = result["word_diagnostics_only"]
    assert w["pairwise_counts"]["canary_vs_whisper"]["word_same_wrong_agreement"] == 1
    assert w["three_same_correct"] == 0
    assert w["not_for_authorization"] is True


def test_three_identically_wrong_word_sequences_are_not_marked_correct():
    observations = {
        f: [{"text": "Stäng av relä 4"}]
        for f in ("parakeet", "canary", "whisper")
    }
    summary = paired_exact_agreement(observations, ["Stäng inte av relä 4"])
    assert summary["word_diagnostics_only"]["three_same_wrong"] == 1
    assert summary["word_diagnostics_only"]["three_same_correct"] == 0
    assert summary["wrong_agreement_is_never_authorization"] is True
