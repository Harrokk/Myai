"""No-network tests of immutable hosted public release manifest and WER math."""
from dataclasses import replace
import hashlib

import pytest

from core.voice_candidate_hosted_manifest import (
    HOSTED_ARTIFACTS, PINNED_CANARY, PINNED_WHISPER,
    validate_hosted_manifest,
)
from scripts.ci_native_model_backed_swedish_smoke import (
    norm_tokens, word_error_rate, verify_downloaded_artifact,
)


def test_two_distinct_pinned_public_model_families():
    arts = validate_hosted_manifest()
    assert len(arts) == 2
    assert set(a.profile for a in arts) == {
        "canary-1b-v2-q8", "whisper-large-v3-turbo",
    }
    assert all(len(a.sha256) == 64 and len(a.revision) == 40 for a in arts)
    assert all(a.url.startswith("https://huggingface.co/") for a in arts)
    assert all("/resolve/main/" not in a.url for a in arts)


def test_exact_canary_public_metadata():
    assert PINNED_CANARY.filename == "canary-1b-v2-Q8_0.gguf"
    assert PINNED_CANARY.byte_size == 1144290016
    assert PINNED_CANARY.sha256 == (
        "224f83d1bc487b3303b495a7d6874912fdece93de19d1a04b550829c30a5d289"
    )
    assert PINNED_CANARY.license == "cc-by-4.0"


def test_exact_whisper_public_metadata():
    assert PINNED_WHISPER.filename == "ggml-large-v3-turbo.bin"
    assert PINNED_WHISPER.byte_size == 1624555275
    assert PINNED_WHISPER.sha256 == (
        "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"
    )
    assert PINNED_WHISPER.license == "mit"


@pytest.mark.parametrize("field,value", [
    ("repository", "evil/../../etc"),
    ("revision", "main"),
    ("revision", "../branch"),
    ("sha256", "0"*63),
    ("sha256", "0"*64 + "G"),
    ("filename", "../bad.gguf"),
    ("filename", "/etc/passwd"),
    ("byte_size", 0),
    ("byte_size", 3 * 10**9),
    ("license", "unknown"),
    ("profile", "third_party_stt"),
])
def test_unreviewed_download_params_do_not_validate(field, value):
    changed = replace(PINNED_CANARY, **{field: value})
    with pytest.raises(ValueError):
        changed.validate()


def test_download_url_is_derived_from_reviewed_commit_and_filename():
    assert PINNED_CANARY.url == (
        "https://huggingface.co/handy-computer/canary-1b-v2-gguf/"
        "resolve/58d13c2c0102229aad45f7e19a77ddc42b41dd9a/"
        "canary-1b-v2-Q8_0.gguf"
    )
    assert PINNED_WHISPER.url.endswith("/ggml-large-v3-turbo.bin")


def test_wer_preserves_swedish_negation_and_diacritics():
    assert word_error_rate("stäng inte av lampan",
                           "Stäng inte av lampan.") == 0.0
    assert word_error_rate("stäng inte av lampan",
                           "stäng av lampan") == 0.25
    assert norm_tokens("ÄR det på?") == ["är", "det", "på"]
    assert word_error_rate("är det på", "ar det pa") > 0


def test_wer_substitution_and_insertion():
    assert word_error_rate("visa ram", "visa minne") == 0.5
    assert word_error_rate("visa ram", "visa ram nu") == 0.5


def test_wer_refuses_blank_reference():
    with pytest.raises(ValueError):
        word_error_rate("", "hallå")


def test_corrupt_or_truncated_file_never_counts_as_pinned_model(tmp_path):
    p = tmp_path / PINNED_CANARY.filename
    p.write_bytes(b"not a real model")
    with pytest.raises(ValueError):
        verify_downloaded_artifact(PINNED_CANARY, p)


def test_symlink_file_denied_even_with_forged_manifest(tmp_path):
    p = tmp_path / "real.bin"
    p.write_bytes(b"dummy")
    alias = tmp_path / "alias.bin"
    alias.symlink_to(p)
    class Fake:
        filename = "alias.bin"
        byte_size = 5
        sha256 = hashlib.sha256(b"dummy").hexdigest()
        def validate(self):
            return self
    with pytest.raises(ValueError):
        verify_downloaded_artifact(Fake(), alias)


def test_runner_guard_requires_hosted_and_arm64(monkeypatch):
    from scripts.ci_native_model_backed_swedish_smoke import require_hosted_runner
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "self-hosted")
    with pytest.raises(RuntimeError, match="hosted ARM64"):
        require_hosted_runner()
