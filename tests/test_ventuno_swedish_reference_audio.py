"""Wikimedia Swedish audio fixture SHA, license and no-user-audio safeguards."""
from pathlib import Path
from types import SimpleNamespace

import pytest

import scripts.ventuno_swedish_reference_audio as audio


def test_exact_fixture_identity_and_license():
    assert audio.SOURCE.startswith("https://upload.wikimedia.org/")
    assert "Sv-svenska.ogg" in audio.SOURCE
    assert len(audio.EXPECTED_SHA1) == 40
    assert "CC BY-SA" in audio.CREDIT
    assert not audio.validate_swedish_sample(b"OggS" + b"0" * 22875)


def test_no_download_into_existing_name(monkeypatch, tmp_path):
    (tmp_path / "myai-whisper-swedish-word.ogg").write_text("do not overwrite")
    monkeypatch.setattr(audio.urllib.request, "urlopen", lambda *a, **kw:
                        pytest.fail("must not fetch with existing file"))
    report = audio.download_fixture(tmp_path)
    assert report["status"] == "reject-existing-swedish-audio"
    assert report["microphone_opened"] is False


def test_unverified_audio_never_written(monkeypatch, tmp_path):
    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def geturl(self):
            return audio.SOURCE
        def read(self, _limit):
            return b"OggS" + b"x" * 100
    monkeypatch.setattr(audio.urllib.request, "urlopen", lambda *a, **kw: Reply())
    report = audio.download_fixture(tmp_path)
    assert report["status"] == "public-sample-integrity-mismatch"
    assert not (tmp_path / "myai-whisper-swedish-word.ogg").exists()
    assert report["user_audio_uploaded"] is False


def test_redirect_to_another_domain_is_refused(monkeypatch, tmp_path):
    class Reply:
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False
        def geturl(self):
            return "https://example.invalid/private"
    monkeypatch.setattr(audio.urllib.request, "urlopen", lambda *a, **kw: Reply())
    result = audio.download_fixture(tmp_path)
    assert result["status"] == "reject-audio-redirect"


def test_unavailable_public_audio_not_fatal_to_production(monkeypatch, tmp_path):
    monkeypatch.setattr(
        audio.urllib.request, "urlopen",
        lambda *a, **kw: (_ for _ in ()).throw(OSError("offline"))
    )
    report = audio.download_fixture(tmp_path)
    assert report["status"] == "public-sample-download-unavailable"
    assert report["microphone_opened"] is False
    assert report["user_audio_uploaded"] is False
