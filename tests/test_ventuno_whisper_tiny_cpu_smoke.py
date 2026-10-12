"""Whisper Tiny staging gates: pinned multilingual model, no microphone/GenieX."""
import hashlib
import json

import pytest

import scripts.ventuno_whisper_tiny_cpu_smoke as m


def test_pinned_multilingual_model_not_tiny_en():
    assert m.REPO == "Systran/faster-whisper-tiny"
    assert len(m.REVISION) == 40
    assert set(m.EXPECTED_FILES) == {
        "model.bin", "config.json", "tokenizer.json", "vocabulary.txt",
    }
    assert "microphone" not in m._RUN
    assert 'language="sv"' in m._RUN
    assert "WhisperModel(" in m._RUN
    assert "local_files_only=True" in m._RUN
    assert "device=\"cpu\"" in m._RUN


def test_pinned_download_limited_to_four_files():
    assert "allow_patterns=" in m._DOWNLOAD
    assert "revision=" in m._DOWNLOAD
    assert "Systran/faster-whisper-tiny" in m._DOWNLOAD
    assert "faster-whisper-tiny.en" not in m._DOWNLOAD


def test_folder_must_be_new_inside_runner(tmp_path):
    folder = tmp_path / "myai-whisper-tiny-model"
    assert m.new_isolated_directory(folder, tmp_path) is True
    folder.mkdir()
    assert m.new_isolated_directory(folder, tmp_path) is False
    assert m.new_isolated_directory(
        tmp_path / "elsewhere", tmp_path
    ) is False


def test_resource_gate_disallows_invoking_whisper(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "mem_available_kib", lambda: 120_000)
    monkeypatch.setattr(m, "disk_free_bytes", lambda _: 50_000_000_000)
    monkeypatch.setattr(m, "run_restricted", lambda *a, **kw:
                        pytest.fail("must not download under RAM pressure"))
    result = m.smoke(tmp_path / "venv" / "bin" / "python", tmp_path,
                     machine="aarch64")
    assert result["cpu_inference_verified"] is False
    assert result["status"] == "no-go-whisper-tiny-benchmark"


def test_wrong_architecture_never_runs(monkeypatch, tmp_path):
    monkeypatch.setattr(m, "mem_available_kib", lambda: 20_000_000)
    monkeypatch.setattr(m, "disk_free_bytes", lambda _: 50_000_000_000)
    monkeypatch.setattr(m, "run_restricted", lambda *a, **kw:
                        pytest.fail("must not download on host x86"))
    report = m.smoke(tmp_path / "venv" / "bin" / "python", tmp_path,
                     machine="x86_64")
    assert report["status"] == "no-go-whisper-tiny-benchmark"


def test_unverified_existing_model_dir_cannot_be_used(monkeypatch, tmp_path):
    py = tmp_path / "myai-voice-staging" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("mock")
    (tmp_path / "myai-whisper-tiny-model").mkdir()
    monkeypatch.setattr(m, "mem_available_kib", lambda: 20_000_000)
    monkeypatch.setattr(m, "disk_free_bytes", lambda _: 50_000_000_000)
    monkeypatch.setattr(m, "run_restricted", lambda *a, **kw:
                        pytest.fail("must not touch existing data"))
    report = m.smoke(py, tmp_path, machine="aarch64")
    assert report["status"] == "reject-non-isolated-or-existing-model-files"


def test_model_binary_range_and_no_symlinks(tmp_path):
    folder = tmp_path / "model"
    folder.mkdir()
    for n in m.EXPECTED_FILES:
        (folder / n).write_bytes(b"ok")
    assert m.model_integrity(folder)["model_metadata_complete"] is False
    (folder / "model.bin").unlink()
    (folder / "model.bin").symlink_to(folder / "tokenizer.json")
    assert m.model_integrity(folder)["model_metadata_complete"] is False


def test_download_failure_keeps_services_unmodified(monkeypatch, tmp_path):
    py = tmp_path / "myai-voice-staging" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("mock")
    monkeypatch.setattr(m, "mem_available_kib", lambda: 20_000_000)
    monkeypatch.setattr(m, "disk_free_bytes", lambda _: 50_000_000_000)
    monkeypatch.setattr(m, "run_restricted", lambda *a, **kw: {
        "succeeded": False, "reason": "timeout"
    })
    report = m.smoke(py, tmp_path, machine="aarch64")
    assert report["status"] == "model-download-unavailable"
    assert report["geniex_restarted"] is False
    assert report["model_installed_in_production"] is False
    assert report["microphone_used"] is False


def test_reject_unverified_inference_result(monkeypatch, tmp_path):
    py = tmp_path / "myai-voice-staging" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("mock")
    monkeypatch.setattr(m, "mem_available_kib", lambda: 20_000_000)
    monkeypatch.setattr(m, "disk_free_bytes", lambda _: 50_000_000_000)
    monkeypatch.setattr(m, "model_integrity", lambda _: {
        "model_metadata_complete": True, "model_sha256": "f" * 64
    })
    attempts = iter([
        {"succeeded": True, "result": {"download_complete": True}},
        {"succeeded": True, "result": {"model_created_on_cpu": True,
                                        "language_requested": "xx"}}
    ])
    monkeypatch.setattr(m, "run_restricted", lambda *a, **kw: next(attempts))
    result = m.smoke(py, tmp_path, machine="aarch64")
    assert result["status"] == "reject-invalid-cpu-inference-measurement"
    assert result["cpu_inference_verified"] is False


def test_reject_nonjson_child_stdout_without_propagating_contents(monkeypatch, tmp_path):
    class Finished:
        returncode = 0
        stdout = "secrets should not be printed"
        stderr = "private traceback"
    monkeypatch.setattr(m.subprocess, "run", lambda *a, **kw: Finished())
    result = m.run_restricted(
        tmp_path / "python", "print('secret')", tmp_path, tmp_path / "model",
        timeout=1, inference=False,
    )
    assert result == {"succeeded": False, "reason": "invalid-reported-result"}
