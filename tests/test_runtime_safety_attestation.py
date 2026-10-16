"""Checks in-process privacy-safe setting snapshot without devices."""
import json

from core.config import DEFAULT_SETTINGS
from core.runtime_safety_attestation import FLAGS, summarize
from scripts.ventuno_isolated_voice_stage_contract import candidate
from scripts.ventuno_physical_pilot_gate import _get_source_profile
from scripts.ventuno_isolated_voice_stage_contract import SOURCE


def test_isolated_stage_reports_all_off_only_inside_loaded_settings():
    values = candidate(json.loads(SOURCE.read_text(encoding="utf-8")))
    report = summarize(values, pid=12345)
    assert report["schema"] == 1
    assert report["process_pid"] == 12345
    assert report["voice_and_writes_off"] is True
    assert report["checks"]["isolated_test_database"] is True
    assert all(value is True for value in report["checks"].values())
    assert "memory.db" not in json.dumps(report)
    assert "geniex" not in json.dumps(report)
    assert report["credentials_exported"] is False


def test_normal_default_config_is_not_reported_safe_for_voice_pilot():
    report = summarize(DEFAULT_SETTINGS, pid=1)
    assert report["voice_and_writes_off"] is False
    assert report["checks"]["isolated_test_database"] is False
    assert report["checks"]["memory_auto_save_off"] is False


def test_missing_or_malformed_sections_fail_closed_without_crashing():
    for case in ({}, {"voice": None}, {"voice": {"enabled": "false"}}):
        report = summarize(case, pid=-1)
        assert report["voice_and_writes_off"] is False
        assert report["process_pid"] is None
        assert report["device_access_performed_by_attestation"] is False


def test_attestation_has_only_fixed_flags_and_never_secrets():
    case = {"voice": {"enabled": False, "api_key": "SECRET_TOKEN"}}
    report = summarize(case, pid=10)
    assert len(report["checks"]) == len(FLAGS) + 2
    assert all(isinstance(x, bool) for x in report["checks"].values())
    assert "SECRET" not in json.dumps(report)
