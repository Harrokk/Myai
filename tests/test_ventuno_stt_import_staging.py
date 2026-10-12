"""CPU-only STT dependency import resource gates and no-model safeguards."""
import json
from pathlib import Path

import pytest

import scripts.ventuno_stt_import_staging as s


def test_sanitize_import_error_class_and_library():
    r = s.classify_import_failure(
        'Traceback: /home/arduino/private/secret\n'
        'OSError: libgomp.so.1: cannot open shared object file\n'
    )
    assert r["failure"] == "OSError"
    assert r["missing_shared_library"] == "libgomp.so.1"
    assert "private" not in str(r)


def test_missing_wheel_report_disallows_install(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    sandbox = runner / "myai-voice-staging" / "bin" / "python"
    sandbox.parent.mkdir(parents=True)
    sandbox.write_bytes(b"mock")
    monkeypatch.setattr(s, "mem_available_kib", lambda: 10_000_000)
    monkeypatch.setattr(s, "disk_free_bytes", lambda _p: 20_000_000_000)
    monkeypatch.setattr(s, "result_of_command", lambda *a, **kw:
                        pytest.fail("do not attempt pip without report"))
    report = s.stage_stt_import(sandbox, runner, arm=True)
    assert report["status"] == "reject-unverified-wheel-or-venv"
    assert report["stt_model_weights_downloaded"] is False


def test_low_memory_gates_install(monkeypatch, tmp_path):
    monkeypatch.setattr(s, "mem_available_kib", lambda: 150_000)
    monkeypatch.setattr(s, "disk_free_bytes", lambda _p: 20_000_000_000)
    monkeypatch.setattr(s, "result_of_command", lambda *a, **kw:
                        pytest.fail("must not install with low RAM"))
    report = s.stage_stt_import(tmp_path / "python", tmp_path, arm=True)
    assert report["stt_python_imports_verified"] is False
    assert report["status"] == "no-go-stt-import-staging"


def test_import_only_with_strict_flags_and_success_rss(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    sandbox = runner / "myai-voice-staging" / "bin" / "python"
    sandbox.parent.mkdir(parents=True)
    sandbox.write_bytes(b"mock")
    report_path = runner / "myai-voice-wheel-report" / "stt-wheel-report.json"
    report_path.parent.mkdir()
    report_path.write_text(json.dumps({
        "install": [{"metadata": {"name": "faster-whisper", "version": "1.2.1"}}]
    }))
    monkeypatch.setattr(s, "mem_available_kib", lambda: 10_000_000)
    monkeypatch.setattr(s, "disk_free_bytes", lambda _p: 20_000_000_000)
    calls = []

    def fake_install(args, **kwargs):
        calls.append(args)
        assert "--only-binary=:all:" in args
        assert "--no-cache-dir" in args
        assert "--dry-run" not in args
        assert "faster-whisper>=1,<2" in args
        assert "av>=17,<19" in args
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["timeout"] <= 200
        return {"completed": True, "exit_zero": True, "exit_code": 0}

    monkeypatch.setattr(s, "result_of_command", fake_install)
    monkeypatch.setattr(s, "import_probe_command", lambda *a, **kw: {
        "imports_ok": True, "peak_rss_mib": 142.3,
        "stt_model_instantiated": False, "htp_npu_used": False
    })
    result = s.stage_stt_import(sandbox, runner, arm=True)
    assert result["status"] == "stt-package-imports-verified-without-model"
    assert result["stt_python_imports_verified"] is True
    assert result["stt_import_peak_rss_mib"] == 142.3
    assert result["stt_model_instantiated"] is False
    assert result["geniex_service_modified"] is False
    assert len(calls) == 1


def test_import_fail_is_no_go_even_if_wheels_installed(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    py = runner / "myai-voice-staging" / "bin" / "python"
    py.parent.mkdir(parents=True)
    py.write_text("fake")
    report_file = runner / "myai-voice-wheel-report" / "stt-wheel-report.json"
    report_file.parent.mkdir()
    report_file.write_text(json.dumps({"install": [
        {"metadata": {"name": "ctranslate2", "version": "4.8.2"}}
    ]}))
    monkeypatch.setattr(s, "mem_available_kib", lambda: 10_000_000)
    monkeypatch.setattr(s, "disk_free_bytes", lambda _p: 20_000_000_000)
    monkeypatch.setattr(s, "result_of_command", lambda *a, **kw: {
        "completed": True, "exit_zero": True, "exit_code": 0
    })
    monkeypatch.setattr(s, "import_probe_command", lambda *a, **kw: {
        "imports_ok": False, "failure": "OSError", "missing_shared_library": "libgomp.so.1"
    })
    result = s.stage_stt_import(py, runner, arm=True)
    assert result["status"] == "stt-optional-import-dependency-unavailable"
    assert result["stt_python_imports_verified"] is False
    assert result["geniex_service_modified"] is False


def test_import_script_never_contains_whisper_model_instantiation():
    from inspect import getsource
    source = getsource(s.import_probe_command)
    assert "WhisperModel(" not in source
    assert "model.transcribe" not in source
    assert "RawInputStream" not in source
