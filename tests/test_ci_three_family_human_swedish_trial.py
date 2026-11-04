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
