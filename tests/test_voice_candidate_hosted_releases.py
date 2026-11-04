"""Hosted model release pins are immutable source data, not user URLs."""
from dataclasses import FrozenInstanceError
import pytest

from core.voice_candidate_hosted_releases import hosted_model_release


@pytest.mark.parametrize("profile,family,license", [
    ("canary-1b-v2-q8", "canary", "cc-by-4.0"),
    ("whisper-large-v3-turbo", "whisper", "mit"),
])
def test_pinned_release_has_exact_revision_hash_size_and_license(
    profile, family, license,
):
    item = hosted_model_release(profile)
    assert item.family == family
    assert item.license == license
    assert len(item.revision) == 40
    assert len(item.sha256) == 64
    assert item.url.startswith("https://huggingface.co/")
    assert "/resolve/main/" not in item.url
    assert item.revision in item.url
    assert item.url.endswith("/" + item.filename)
    assert 1_000_000 < item.bytes < 2_000_000_000
    assert len(item.native_source_revision) == 40


@pytest.mark.parametrize("input", [
    None, 3, "", "main", "canary-1b-v2-q8/../../../../tmp",
    "http://evil.example.com", "whisper", "canary-1b-v2-q8\n",
])
def test_manifest_does_not_accept_unreviewed_model_or_injection(input):
    with pytest.raises(ValueError, match="Unknown hosted-only"):
        hosted_model_release(input)


def test_release_fields_cannot_be_reassigned_or_downgraded():
    model = hosted_model_release("canary-1b-v2-q8")
    with pytest.raises(FrozenInstanceError):
        model.sha256 = "0" * 64
    with pytest.raises(FrozenInstanceError):
        model.revision = "main"


def test_exact_published_canary_sha256_is_pinned():
    m = hosted_model_release("canary-1b-v2-q8")
    assert m.sha256 == (
        "224f83d1bc487b3303b495a7d6874912fdece93de19d1a04b550829c30a5d289"
    )
    assert m.bytes == 1144290016


def test_exact_published_whisper_sha256_is_pinned():
    m = hosted_model_release("whisper-large-v3-turbo")
    assert m.sha256 == (
        "1fc70f774d38eb169993ac391eea357ef47c88757ef72ee5943879b7e8e2bc69"
    )
    assert m.bytes == 1624555275


def test_two_model_families_and_two_sources_are_distinct():
    a = hosted_model_release("canary-1b-v2-q8")
    b = hosted_model_release("whisper-large-v3-turbo")
    assert a.family != b.family
    assert a.repository != b.repository
    assert a.sha256 != b.sha256
    assert a.native_source_revision != b.native_source_revision
