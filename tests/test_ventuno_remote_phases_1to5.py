"""Offline source-only readiness ledger regression tests."""
from scripts.ventuno_remote_phases_1to5 import inspect


def test_reviewed_remote_sources_ready_but_real_tests_remain_blocked():
    report = inspect()
    assert report["status"] == "source-only-phases-1-to-5-ready"
    assert report["legacy_workflows_quarantined"]
    assert report["all_28_wheel_hashes_source_locked"]
    assert report["isolated_profile_risk_switches_off"]
    for key in ("isolated_native_venv_installed",
                "synthetic_stt_tts_e2e_executed",
                "live_effective_config_attested",
                "crash_recovery_physically_tested",
                "npu_htp_authorized", "audio_capture_authorized",
                "release_deployed"):
        assert report[key] is False


def test_missing_source_fails_closed(tmp_path):
    report = inspect(tmp_path)
    assert report["status"] == "blocked-source-preflight"
    assert report["npu_htp_authorized"] is False
