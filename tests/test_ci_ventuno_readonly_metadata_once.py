"""No-board unit tests for the one-time GitHub-runner metadata bridge."""
from types import SimpleNamespace
import json

import pytest

from scripts.ci_ventuno_readonly_metadata_once import (
    _call_module, summarize, main,
)


def source_reports():
    pilot = {
        "status": "board-readonly-preflight-passed",
        "source_exact_sha": True,
        "source_config_default_off": True,
        "active_production_profile_default_off": True,
        "board_preflight_passed": True,
        "ready_for_separate_human_consent": True,
        "recording_authorized": False,
        "playback_authorized": False,
        "physical_recording_attempted": False,
        "model_loaded": False,
        "npu_tested": False,
        "production_changed": False,
    }
    idle = {
        "status": "read-only-idle-baseline",
        "myai_service_active": True,
        "geniex_service_active": True,
        "runner_service_active": True,
        "microphone_opened": False,
        "services_modified": False,
        "usb_audio_present": True,
        "ram_available_gib": 13.1,
        "disk_available_gib": 34.7,
        "temperature_max_c": 43.0,
    }
    matrix = {
        "status": "metadata-completed-needs-operator-test",
        "board_usb_voice_metadata_ready": True,
        "read_only_npu_metadata_valid": True,
        "read_only_htp_capture_metadata_valid": True,
        "read_only_htp_concurrency_metadata_valid": True,
        "read_only_recovery_dryrun_metadata_valid": True,
        "all_five_probe_reports_present": True,
        "safe_to_request_separate_voice_consent": True,
        "physical_audio_authorized": False,
        "exclusive_npu_maintenance_authorized": False,
        "real_microphone_audio_tested_now": False,
        "real_speaker_playback_tested_now": False,
        "system_services_changed": False,
    }
    return pilot, idle, matrix


def test_board_metadata_is_not_audio_consent_even_if_all_reports_accept():
    p, i, m = source_reports()
    report = summarize(p, i, m)
    assert report["status"] == "board-readonly-metadata-accepted"
    assert report["physical_recording_authorized"] is False
    assert report["physical_playback_authorized"] is False
    assert report["npu_inference_performed"] is False
    assert report["critical_tool_execution_authorized"] is False
    assert report["live_model_inference_performed"] is False
    assert report["production_modified"] is False
    assert report["separate_operator_consent_required"] is True
    assert report["ram_available_gib"] == 13.1
    assert report["temperature_max_c"] == 43.0


@pytest.mark.parametrize("name,field,value", [
    ("pilot", "source_exact_sha", False),
    ("pilot", "active_production_profile_default_off", False),
    ("pilot", "recording_authorized", True),
    ("pilot", "status", "blocked-usb-reenumerated-or-inaccessible"),
    ("idle", "geniex_service_active", False),
    ("idle", "runner_service_active", False),
    ("idle", "microphone_opened", True),
    ("idle", "usb_audio_present", False),
    ("matrix", "physical_audio_authorized", True),
    ("matrix", "read_only_htp_concurrency_metadata_valid", False),
    ("matrix", "status", "incomplete-or-unsafe-metadata"),
])
def test_any_unexpected_hardware_activity_or_unsafe_flag_blocks(name, field, value):
    p, i, m = source_reports()
    report = {"pilot": p, "idle": i, "matrix": m}[name]
    report[field] = value
    verdict = summarize(p, i, m)
    assert verdict["status"] == "blocked-readonly-hardware-preflight"
    assert verdict["physical_recording_authorized"] is False


@pytest.mark.parametrize("bad", [None, [], "text", 3, {}])
def test_untrusted_probe_response_types_never_authorize(bad):
    p, i, m = source_reports()
    assert summarize(bad, i, m)["status"].startswith("blocked")
    assert summarize(p, bad, m)["status"].startswith("blocked")
    assert summarize(p, i, bad)["status"].startswith("blocked")


def test_probe_captures_output_but_does_not_log_raw_text(tmp_path):
    def fake_run(argv, **kwargs):
        assert kwargs["capture_output"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 12
        assert "GITHUB_TOKEN" not in kwargs["env"]
        return SimpleNamespace(
            returncode=0,
            stdout='MYAI_TEST=' + json.dumps({"status": "read-only-idle-baseline"}),
            stderr="private audio text MUST NEVER be emitted",
        )
    result = _call_module(
        tmp_path, "scripts.synthetic", [],
        "MYAI_TEST=", python=tmp_path / "python",
        executor=fake_run, time_limit=12,
    )
    assert result == {"status": "read-only-idle-baseline"}


@pytest.mark.parametrize("ret,stdout", [
    (2, "invalid json"),
    (1, '{"status":"board-readonly-preflight-passed"}'),
    (0, "MYAI_TEST=" + "x" * 33000),
    (0, "MYAI_TEST={}\nMYAI_TEST={}"),
    (0, "MYAI_TEST=" + json.dumps({"status": 12})),
])
def test_invalid_nonbounded_or_exit_code_probe_fails_closed(tmp_path, ret, stdout):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(returncode=ret, stdout=stdout, stderr="")
    result = _call_module(
        tmp_path, "scripts.synthetic", [], "MYAI_TEST=",
        python=tmp_path / "python", executor=fake_run,
    )
    assert result["status"].startswith("probe-")


def test_nonselfhosted_invocation_never_inspects_board(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("RUNNER_ENVIRONMENT", "github-hosted")
    monkeypatch.setenv("GITHUB_REPOSITORY", "Harrokk/Myai")
    monkeypatch.setenv("GITHUB_REF",
                       "refs/heads/dev/ventuno-physical-readonly-once-20261104")
    result = main(["--source-root", str(tmp_path), "--expected-sha", "f" * 40])
    assert result == 2
    printed = capsys.readouterr().out
    assert "blocked-readonly-hardware-preflight" in printed
    assert '"physical_recording_authorized":false' in printed
    assert '"production_modified":false' in printed
