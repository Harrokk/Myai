"""Safety regression checks for official, bounded QAIRT archive fetcher."""
from pathlib import Path

import pytest

import scripts.fetch_qairt_245_official as mod


def test_official_qualcomm_https_urls_only():
    assert mod.allowed_redirect(mod.URL)
    assert mod.allowed_redirect("https://download.qualcomm.com/file.zip")
    for bad in ("http://softwarecenter.qualcomm.com/z",
                "https://softwarecenter.qualcomm.com.evil.net/z",
                "https://example.org/sdk.zip", "file:///tmp/test"):
        assert not mod.allowed_redirect(bad)


def test_no_download_on_nonhost(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "aarch64")
    monkeypatch.setattr(mod, "urlopen",
                        lambda *a, **k: pytest.fail("attempted internet"))
    out = mod.fetch_known_sdk(tmp_path / "sdk.zip")
    assert out["status"] == "reject-nonhost-architecture"
    assert out["production_services_changed"] is False


def test_no_download_when_disk_insufficient(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "free_space_enough", lambda p: False)
    monkeypatch.setattr(mod, "urlopen",
                        lambda *a, **k: pytest.fail("attempted internet"))
    out = mod.fetch_known_sdk(tmp_path / "sdk.zip")
    assert out["status"] == "reject-insufficient-free-space"


def test_no_overwrite_existing_target(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    dest = tmp_path / "sdk.zip"
    dest.write_bytes(b"unchanged")
    monkeypatch.setattr(mod, "urlopen",
                        lambda *a, **k: pytest.fail("attempted internet"))
    out = mod.fetch_known_sdk(dest)
    assert out["status"] == "reject-unsafe-output-target"
    assert dest.read_bytes() == b"unchanged"


def test_pretend_qualcomm_size_too_big_rejected(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "free_space_enough", lambda p: True)

    class Fake:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def geturl(self):
            return mod.URL
        headers = {"Content-Length": str(mod.MAX_BYTES + 1)}
    monkeypatch.setattr(mod, "urlopen", lambda *a, **k: Fake())
    out = mod.fetch_known_sdk(tmp_path / "sdk.zip")
    assert out["status"] == "reject-oversize-content-length"
    assert not (tmp_path / "sdk.zip").exists()


def test_wrong_host_refuses_without_download(monkeypatch, tmp_path):
    monkeypatch.setattr(mod.platform, "machine", lambda: "x86_64")
    monkeypatch.setattr(mod, "free_space_enough", lambda p: True)

    class Fake:
        def __enter__(self):
            return self
        def __exit__(self, *args):
            pass
        def geturl(self):
            return "https://unsafe.example.com/sdk.zip"
        headers = {}
    monkeypatch.setattr(mod, "urlopen", lambda *a, **k: Fake())
    out = mod.fetch_known_sdk(tmp_path / "sdk.zip")
    assert out["status"] == "reject-external-download-redirect"
    assert not (tmp_path / "sdk.zip").exists()
