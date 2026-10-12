"""Staging-only faster-whisper wheel preflight never loads STT weights."""
import json

import pytest

import scripts.ventuno_stt_wheel_preflight as stt


def test_wheel_metadata_report_filters_names_and_urls(tmp_path):
    path = tmp_path / "wheel-report.json"
    path.write_text(json.dumps({
        "install": [
            {"metadata": {"name": "faster-whisper", "version": "1.2.1"},
             "download_info": {"url": "https://credentials.private/path"}},
            {"metadata": {"name": "ctranslate2", "version": "4.6.0"}},
            {"metadata": {"name": "some-unneeded-private-wheel", "version": "1"}},
        ],
    }))
    report = stt.inspect_resolve_report(path)
    assert report["report_generated"] is True
    assert report["candidate_package_count"] == 3
    assert report["key_wheel_versions"] == {
        "faster-whisper": "1.2.1", "ctranslate2": "4.6.0"
    }
    assert "credentials" not in str(report)
    assert "some-unneeded" not in str(report)


def test_missing_invalid_report_is_inconclusive(tmp_path):
    p = tmp_path / "missing"
    assert stt.inspect_resolve_report(p)["report_generated"] is False
    p.write_text("{invalid json")
    assert stt.inspect_resolve_report(p)["report_generated"] is False


def test_reject_unverified_python_without_any_pip(monkeypatch, tmp_path):
    monkeypatch.setattr(stt, "mem_available_kib", lambda: 4_000_000)
    monkeypatch.setattr(stt, "disk_free_bytes", lambda _: 4_000_000_000)
    monkeypatch.setattr(stt, "result_of_command", lambda *a, **kw:
                        pytest.fail("no pip must run with arbitrary python"))
    p = tmp_path / "python"
    p.write_text("dummy")
    outcome = stt.dry_run(p, tmp_path, arm=True)
    assert outcome["status"] == "reject-non-isolated-python"
    assert outcome["faster_whisper_installed"] is False


def test_ram_gate_prevents_whisper_wheel_download(monkeypatch, tmp_path):
    monkeypatch.setattr(stt, "mem_available_kib", lambda: 300_000)
    monkeypatch.setattr(stt, "disk_free_bytes", lambda _: 5_000_000_000)
    monkeypatch.setattr(stt, "result_of_command", lambda *a, **kw:
                        pytest.fail("no pip in resource constrained system"))
    result = stt.dry_run(tmp_path / "python", tmp_path, arm=True)
    assert result["status"] == "no-go-stt-wheel-resolution"
    assert result["wheel_resolution_succeeded"] is False


def test_pip_resolution_uses_dry_run_only(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    python = runner / "myai-voice-staging" / "bin" / "python"
    python.parent.mkdir(parents=True)
    python.write_text("placeholder")
    monkeypatch.setattr(stt, "mem_available_kib", lambda: 5_000_000)
    monkeypatch.setattr(stt, "disk_free_bytes", lambda _: 12_000_000_000)
    captured = []

    def fake_run(args, **kwargs):
        captured.append(args)
        assert "--dry-run" in args
        assert "--only-binary=:all:" in args
        assert "--ignore-installed" in args
        assert "--no-cache-dir" in args
        assert "install" in args
        assert kwargs["env"]["HF_HUB_OFFLINE"] == "1"
        assert kwargs["timeout"] <= 135
        path = runner / "myai-voice-wheel-report" / "stt-wheel-report.json"
        path.write_text(json.dumps({"install": [
            {"metadata": {"name": "faster-whisper", "version": "1.2.1"}},
            {"metadata": {"name": "ctranslate2", "version": "4.6.0"}},
        ]}))
        return {"exit_zero": True, "completed": True, "exit_code": 0}

    monkeypatch.setattr(stt, "result_of_command", fake_run)
    report = stt.dry_run(python, runner, arm=True)
    assert len(captured) == 1
    assert report["status"] == "faster-whisper-arm64-wheels-resolved-no-install"
    assert report["wheel_resolution_succeeded"] is True
    assert report["faster_whisper_installed"] is False
    assert report["stt_model_weights_downloaded"] is False
    assert report["geniex_service_changed"] is False


def test_empty_report_is_not_wheel_proof(monkeypatch, tmp_path):
    runner = tmp_path / "runner"
    p = runner / "myai-voice-staging" / "bin" / "python"
    p.parent.mkdir(parents=True)
    p.write_text("placeholder")
    monkeypatch.setattr(stt, "mem_available_kib", lambda: 5_000_000)
    monkeypatch.setattr(stt, "disk_free_bytes", lambda _: 5_000_000_000)
    monkeypatch.setattr(stt, "result_of_command", lambda *a, **kw: {
        "exit_zero": True, "completed": True, "exit_code": 0
    })
    report = stt.dry_run(p, runner, arm=True)
    assert report["wheel_resolution_succeeded"] is False
