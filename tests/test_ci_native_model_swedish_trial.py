"""All downloads mocked: no real model or network in source-only tests."""
import hashlib
import io
from types import SimpleNamespace

import pytest

import scripts.ci_fetch_pinned_stt_model as fetch
from scripts.ci_native_model_swedish_trial import (
    word_error_count, words,
)


@pytest.mark.parametrize("url,expected", [
    ("https://huggingface.co/handy/repo/resolve/abc/model.gguf", True),
    ("https://cas-bridge.xethub.hf.co/reconstruction/abc", True),
    ("https://cdn-lfs.huggingface.co/abc", True),
    ("http://huggingface.co/file", False),
    ("https://huggingface.co.evil.example/file", False),
    ("https://127.0.0.1/model", False),
    ("https://localhost/model", False),
    ("https://huggingface.co:8443/file", False),
    ("https://username:password@huggingface.co/file", False),
    ("file:///etc/passwd", False),
    ("https://hf.co/file#fragment", False),
    ("https://evil.example/hf.co/file", False),
])
def test_public_model_url_allowlist_rejects_ssrf_and_userinfo(url, expected):
    assert fetch._trusted_model_url(url) is expected


def test_redirect_class_rejects_untrusted_host_without_network():
    handler = fetch._PinnedModelRedirect()
    with pytest.raises(ValueError, match="Untrusted pinned model redirect"):
        handler.redirect_request(
            None, None, 302, "redirect", {},
            "http://127.0.0.1/latest/meta-data",
        )


def synthetic_release(raw, *, digest=None):
    return SimpleNamespace(
        profile="canary-1b-v2-q8",
        filename="synthetic-test.gguf",
        bytes=len(raw),
        sha256=digest or hashlib.sha256(raw).hexdigest(),
        url="https://huggingface.co/handy-computer/test/resolve/"
            + "a" * 40 + "/synthetic-test.gguf",
    )


class FakeResponse:
    status = 200

    def __init__(self, raw):
        self.data = io.BytesIO(raw)

    def read(self, count):
        return self.data.read(count)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, exc_tb):
        return False


class FakeOpener:
    def __init__(self, raw):
        self.raw = raw

    def open(self, request, timeout):
        return FakeResponse(self.raw)


def test_correct_exact_model_bytes_are_hash_verified(tmp_path, monkeypatch):
    data = b"A" * 1000001
    expected = synthetic_release(data)
    monkeypatch.setattr(fetch, "hosted_model_release", lambda name: expected)
    monkeypatch.setattr(fetch, "build_opener", lambda *_a: FakeOpener(data))
    path, result = fetch.download_hosted_model(expected.profile, str(tmp_path))
    assert result is expected
    model_path = path / expected.filename
    assert model_path.read_bytes() == data
    assert model_path.stat().st_mode & 0o222 == 0
    assert path.stat().st_mode & 0o222 == 0
    path.chmod(0o755)


def test_wrong_digest_cleans_partial_download(tmp_path, monkeypatch):
    data = b"A" * 1000001
    bad = synthetic_release(data, digest="0" * 64)
    monkeypatch.setattr(fetch, "hosted_model_release", lambda name: bad)
    monkeypatch.setattr(fetch, "build_opener", lambda *_a: FakeOpener(data))
    with pytest.raises(ValueError, match="SHA256"):
        fetch.download_hosted_model(bad.profile, str(tmp_path))
    assert not (tmp_path / "myai-pinned-model-files" /
                bad.profile / bad.filename).exists()


def test_oversized_download_rejected_before_full_write(tmp_path, monkeypatch):
    data = b"B" * 1000002
    item = synthetic_release(data[:1000001])
    monkeypatch.setattr(fetch, "hosted_model_release", lambda name: item)
    monkeypatch.setattr(fetch, "build_opener", lambda *_a: FakeOpener(data))
    with pytest.raises(ValueError, match="Oversized"):
        fetch.download_hosted_model(item.profile, str(tmp_path))


def test_preexisting_model_directory_never_reused(tmp_path, monkeypatch):
    item = synthetic_release(b"A" * 1000001)
    (tmp_path / "myai-pinned-model-files" / item.profile).mkdir(parents=True)
    monkeypatch.setattr(fetch, "hosted_model_release", lambda name: item)
    monkeypatch.setattr(
        fetch, "build_opener",
        lambda *_a: pytest.fail("download attempted into pre-existing dir"),
    )
    with pytest.raises(ValueError, match="pre-existing"):
        fetch.download_hosted_model(item.profile, str(tmp_path))


def test_swedish_tokenization_retains_negation_and_numbers():
    assert words("Radera INTE fil 17!") == ["radera", "inte", "fil", "17"]
    assert word_error_count("Radera inte fil 17", "Radera fil 18") == (2, 4)


def test_synthetic_single_phrase_word_distance_is_not_quality_certificate():
    assert word_error_count("I dag är vädret fint", "I dag är vädret fint") == (0, 5)
    assert word_error_count("Öppna filen", "Radera filen") == (1, 2)
