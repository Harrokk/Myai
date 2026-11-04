"""Synthetic only: prove hosted source gate never grants physical consent."""
from pathlib import Path

import pytest

from scripts.ci_prephysical_source_gate import (
    _REQUIRED_REVIEWED_FILES, _HISTORICAL_DISABLED_AUDIO_JOBS,
    _security_smoke, _historical_audio_jobs_inert, assess,
)
from scripts.ventuno_physical_pilot_gate import SAFE_FLAGS


COMMIT = "a" * 40


def safe_fixture(tmp_path):
    root = tmp_path / "source"
    root.mkdir()
    profile = {
        name: {flag: False for flag in flags}
        for name, flags in SAFE_FLAGS.items()
    }
    profile["voice"]["risk_tiered_verification_enabled"] = False
    for file in _REQUIRED_REVIEWED_FILES:
        item = root / file
        item.parent.mkdir(parents=True, exist_ok=True)
        item.write_text("# reviewed test-only placeholder\n")
    # Recreate only the source-header and job identity. No device is present.
    for name, job in _HISTORICAL_DISABLED_AUDIO_JOBS:
        file = root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(
            "name: Synthetic inert job\\n"
            "on:\\n  push:\\n    branches: [dev/synthetic]\\n"
            "jobs:\\n"
            f"  {job}:\\n"
            "    if: false\\n"
            "    runs-on: [self-hosted, Linux, ARM64, ventuno-q]\\n"
            "    steps:\\n      - run: echo inert\\n"
        )
    return root, profile


def test_synthetic_security_denial_witnesses_still_fail_closed():
    assert _security_smoke() is True


def test_offhost_gate_never_calls_itself_physical_consent(tmp_path):
    root, profile = safe_fixture(tmp_path)
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["status"] == (
        "hosted-source-ready-for-separate-board-readonly-preflight"
    )
    assert report["source_commit_exact_and_clean"] is True
    assert report["eligible_to_request_separate_board_readonly_preflight"] is True
    assert report["board_physically_inspected_by_this_gate"] is False
    assert report["physical_voice_test_authorized"] is False
    assert report["critical_command_authorized"] is False
    assert report["model_weights_placed_on_ventuno"] is False
    assert report["separate_human_consent_still_required"] is True


@pytest.mark.parametrize("bad_sha", [
    "", "b" * 40, "0" * 39, "a" * 41, "z" * 40, None,
])
def test_source_sha_mismatch_or_invalid_format_is_blocked(tmp_path, bad_sha):
    root, profile = safe_fixture(tmp_path)
    report = assess(root, bad_sha, COMMIT, profile)
    assert report["status"] == "blocked-offhost-prephysical-gates"
    assert report["eligible_to_request_separate_board_readonly_preflight"] is False
    assert report["physical_voice_test_authorized"] is False


@pytest.mark.parametrize("section,flag", [
    ("voice", "enabled"),
    ("voice", "tts_enabled"),
    ("voice", "handsfree_enabled"),
    ("ventuno", "rpc_write_enabled"),
    ("geniex_supervisor", "restart_enabled"),
    ("camera", "enabled"),
    ("selfdev", "promotion_enabled"),
    ("trusted_terminals", "auto_execute"),
    ("excel", "write_enabled"),
])
def test_mutable_or_privacy_sensitive_production_flags_block(tmp_path, section, flag):
    root, profile = safe_fixture(tmp_path)
    profile[section][flag] = True
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["status"] == "blocked-offhost-prephysical-gates"


def test_staged_risk_feature_must_remain_off(tmp_path):
    root, profile = safe_fixture(tmp_path)
    profile["voice"]["risk_tiered_verification_enabled"] = True
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["eligible_to_request_separate_board_readonly_preflight"] is False
    assert report["physical_voice_test_authorized"] is False


def test_absent_audited_file_blocks_prephysical_handoff(tmp_path):
    root, profile = safe_fixture(tmp_path)
    (root / _REQUIRED_REVIEWED_FILES[0]).unlink()
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["required_audited_gate_files_present"] is False
    assert report["status"] == "blocked-offhost-prephysical-gates"


def test_incorrect_profile_shape_fails_closed(tmp_path):
    root, _ = safe_fixture(tmp_path)
    for bad in (None, {}, {"voice": None}, []):
        report = assess(root, COMMIT, COMMIT, bad)
        assert report["physical_voice_test_authorized"] is False
        assert report["status"] == "blocked-offhost-prephysical-gates"


def test_symlinked_gate_file_is_not_accepted(tmp_path):
    root, profile = safe_fixture(tmp_path)
    item = root / _REQUIRED_REVIEWED_FILES[0]
    item.unlink()
    item.symlink_to(root / _REQUIRED_REVIEWED_FILES[1])
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["required_audited_gate_files_present"] is False
    assert report["eligible_to_request_separate_board_readonly_preflight"] is False

@pytest.mark.parametrize("index", [0, 1, 2])
def test_old_selfhosted_audio_job_must_not_be_reactivated(tmp_path, index):
    root, profile = safe_fixture(tmp_path)
    assert _historical_audio_jobs_inert(root) is True
    path, _ = _HISTORICAL_DISABLED_AUDIO_JOBS[index]
    target = root / path
    target.write_text(target.read_text().replace("if: false", "if: true"))
    assert _historical_audio_jobs_inert(root) is False
    report = assess(root, COMMIT, COMMIT, profile)
    assert report["status"] == "blocked-offhost-prephysical-gates"
    assert report["physical_voice_test_authorized"] is False


def test_missing_or_symlinked_inert_audio_job_blocks(tmp_path):
    root, profile = safe_fixture(tmp_path)
    path, _ = _HISTORICAL_DISABLED_AUDIO_JOBS[0]
    file = root / path
    file.unlink()
    assert _historical_audio_jobs_inert(root) is False
    assert assess(root, COMMIT, COMMIT, profile)["status"].startswith("blocked")
