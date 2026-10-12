"""No-model-load Ollama ARM64 readiness and privacy tests."""
import json

import pytest
from pathlib import Path

import scripts.ventuno_ollama_readiness as mod


def _ready(monkeypatch, *, binary="/usr/bin/ollama", server=True,
           model=True, mem=12 * 1024 * 1024,
           disk=30 * 1024 ** 3):
    monkeypatch.setattr(mod.shutil, "which", lambda name: binary)
    monkeypatch.setattr(mod, "_local_json", lambda path: (
        {"version": "0.12.0"} if path == "/api/version" and server else
        {"models": [{"name": "qwen3:0.6b"}] if model else []}
        if path == "/api/tags" and server else None
    ))
    return mod.inspect_ollama(
        machine="aarch64", available_mem_kib=mem, free_disk_bytes=disk,
        user_local_binary=Path("/__nonexistent_test_ollama_bin__"),
    )


def test_ready_existing_small_model_requires_no_download(monkeypatch):
    report = _ready(monkeypatch)
    assert report["status"] == "ready-for-separate-ollama-test"
    assert report["ollama_binary_present"] is True
    assert report["loopback_ollama_api_ready"] is True
    assert report["test_model_already_downloaded"] is True
    assert report["model_loaded"] is False
    assert report["ollama_started"] is False
    assert report["geniex_touched"] is False


def test_existing_server_without_small_model_cannot_claim_ready(monkeypatch):
    report = _ready(monkeypatch, model=False)
    assert report["status"] == "ollama-api-ready-no-small-model"
    assert report["test_model_already_downloaded"] is False


def test_missing_binary_does_not_claim_installation(monkeypatch):
    report = _ready(monkeypatch, binary=None, server=False)
    assert report["status"] == "ollama-not-installed"


def test_binary_present_without_server_is_not_ready(monkeypatch):
    report = _ready(monkeypatch, server=False)
    assert report["status"] == "ollama-binary-present-api-unavailable"


def test_low_ram_is_reported_without_starting_anything(monkeypatch):
    report = _ready(monkeypatch, mem=320_000)
    assert report["spare_memory_for_small_model"] is False
    assert report["model_loaded"] is False


def test_low_disk_is_reported_without_downloading_anything(monkeypatch):
    report = _ready(monkeypatch, disk=100)
    assert report["spare_disk_for_staging"] is False


def test_never_exposes_model_list_or_labels(monkeypatch):
    monkeypatch.setattr(mod.shutil, "which", lambda name: "/usr/bin/ollama")
    monkeypatch.setattr(mod, "_local_json", lambda path: (
        {"version": "private-user-version", "secret": "DO_NOT_LOG"}
        if path == "/api/version"
        else {"models": [
            {"name": "private-user-model", "path": "/private/account/path"},
            {"name": "qwen3:0.6b"},
        ]}
    ))
    report = mod.inspect_ollama(
        machine="aarch64",
        available_mem_kib=10 * 1024 * 1024,
        free_disk_bytes=8 * 1024**3,
    )
    dump = json.dumps(report)
    assert "private-user-version" not in dump
    assert "private-user-model" not in dump
    assert "DO_NOT_LOG" not in dump
    assert "private/account" not in dump


def test_loopback_query_only_uses_two_safe_paths(monkeypatch):
    called = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size):
            return b'{"version":"1.0"}'
    monkeypatch.setattr(mod, "urlopen", lambda url, timeout: (
        called.append((url, timeout)) or Response()
    ))
    assert mod._local_json("/api/version")["version"] == "1.0"
    assert mod._local_json("/api/chat") is None
    assert len(called) == 1
    assert called[0][0] == "http://127.0.0.1:11434/api/version"
    assert called[0][1] <= 2


def test_oversize_response_fails_closed(monkeypatch):
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def read(self, size): return b"x" * (mod.MAX_HTTP_BODY + 1)
    monkeypatch.setattr(mod, "urlopen", lambda *args, **kwargs: Response())
    assert mod._local_json("/api/version") is None


def test_user_local_binary_detected_even_when_path_not_set(monkeypatch,tmp_path):
    installed=tmp_path/"bin"/"ollama"
    installed.parent.mkdir()
    installed.write_text("#!/bin/sh\nexit 0\n")
    installed.chmod(0o700)
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod, "_local_json", lambda _: None)
    result=mod.inspect_ollama(
        machine="aarch64", available_mem_kib=10*1024*1024,
        free_disk_bytes=10*1024**3,
        user_local_binary=installed,
    )
    assert result["status"] == "ollama-binary-present-api-unavailable"
    assert result["ollama_binary_present"] is True
    assert result["model_loaded"] is False


def test_user_local_symlink_is_not_treated_as_verified_binary(monkeypatch,tmp_path):
    real=tmp_path/"not-an-ollama-install"
    real.write_text("not a binary")
    real.chmod(0o700)
    link=tmp_path/"ollama"
    link.symlink_to(real)
    monkeypatch.setattr(mod.shutil, "which", lambda _: None)
    monkeypatch.setattr(mod,"_local_json",lambda _: None)
    result=mod.inspect_ollama(
        machine="aarch64", available_mem_kib=10*1024*1024,
        free_disk_bytes=10*1024**3,
        user_local_binary=link,
    )
    assert result["status"] == "ollama-not-installed"
