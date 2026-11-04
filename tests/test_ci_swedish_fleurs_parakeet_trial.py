"""Offline contracts: SHA-pinned human Swedish evaluation never grants tool consent."""
import pytest

from scripts.ci_swedish_fleurs_parakeet_trial import (
    FLEURS_BYTES, FLEURS_REVISION, FLEURS_SHA256,
    PARAKEET_REVISION, PARAKEET_FILES,
    SAMPLES, decode_public_audio, select_rows, nearest_rank,
)
from scripts.ci_native_model_swedish_trial import word_error_count
from core.voice_verification import _canonical


def test_human_fleurs_swedish_test_split_has_immutable_source_identity():
    assert FLEURS_REVISION == "14b46a200cec86ab4cf963c5c0b4661ef343f34a"
    assert FLEURS_BYTES == 537731833
    assert FLEURS_SHA256 == "efaddda3e8460662b26d07c9fa1e52cbf57fb18365acf5bc232ea1bcf43ed935"


def test_parakeet_int8_model_requires_all_four_sha256_pinned_files():
    assert PARAKEET_REVISION == "2bda32ec70b097a55adaa07d9a7173915b43cc78"
    assert set(PARAKEET_FILES) == {
        "encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx", "tokens.txt",
    }
    assert PARAKEET_FILES["encoder.int8.onnx"][0] == 652184281
    for size, digest in PARAKEET_FILES.values():
        assert type(size) is int and 1000 <= size < 700_000_000
        assert len(digest) == 64 and set(digest) <= set("0123456789abcdef")


def test_exploratory_wer_cannot_equal_security_transcript_consensus():
    assert word_error_count("rapport.txt", "rapport txt")[0] == 0
    assert _canonical("rapport.txt") != _canonical("rapport txt")


def test_p95_has_documented_nearest_rank_behavior():
    assert nearest_rank([1.0, 2.0, 4.0, 7.0], 50) == 2.0
    assert nearest_rank([1.0, 2.0, 4.0, 7.0], 95) == 7.0
    with pytest.raises(ValueError):
        nearest_rank([], 95)


@pytest.mark.parametrize("payload", [b"", b"no", None, 42, b"x" * 6_000_001])
def test_public_audio_decoder_does_not_spawn_on_invalid_payload(payload):
    with pytest.raises(ValueError):
        decode_public_audio(payload)


@pytest.mark.parametrize("limit", [0, -1, 61, "12", True])
def test_dataset_selection_fails_closed_on_invalid_sample_limit(tmp_path, limit):
    with pytest.raises(ValueError):
        list(select_rows(tmp_path / "absent.parquet", limit))


def test_initial_exploratory_sample_count_is_fixed_and_not_an_accuracy_gate():
    assert SAMPLES == 12
