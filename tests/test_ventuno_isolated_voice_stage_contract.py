"""Source-only full physical voice profile stage: no services, audio, or DB."""
import json
from pathlib import Path
import pytest

from core.config import DEFAULT_SETTINGS, _merge_settings
from scripts import ventuno_isolated_voice_stage_contract as stage


def test_exact_staged_profile_matches_reviewed_disabled_contract():
    result = stage.inspect()
    assert result["status"] == "source-only-isolated-stage-contract-passed"
    assert result["source_profile_all_risk_flags_off"] is True
    assert result["stage_profile_all_risk_flags_off"] is True
    assert result["stage_exactly_matches_reviewed_override"] is True
    source = json.loads(stage.SOURCE.read_text())
    generated = stage.candidate(source)
    assert stage.attest(generated) is True
    assert generated["voice"]["stt_process_isolation_enabled"] is True
    assert generated["voice"]["stt_model"] == "tiny"
    assert generated["voice"]["enabled"] is False
    assert generated["memory"]["database"] == stage.STAGING_MEMORY
    assert generated["memory"]["auto_save_enabled"] is False
    assert generated["files"]["write_enabled"] is False
    assert generated["geniex_supervisor"]["restart_enabled"] is False


def test_no_file_db_runtime_ever_created_by_inspect(tmp_path):
    source = tmp_path / "original.json"
    destination = tmp_path / "stage.json"
    source.write_bytes(stage.SOURCE.read_bytes())
    destination.write_bytes(stage.STAGE.read_bytes())
    before = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert stage.inspect(source, destination)["candidate_safe_by_contract"]
    after = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert before == after
    assert not any(x.suffix == ".db" for x in tmp_path.iterdir())


@pytest.mark.parametrize("section,key,value", [
    ("voice", "enabled", True),
    ("voice", "tts_enabled", True),
    ("voice", "handsfree_enabled", True),
    ("voice", "stt_process_isolation_enabled", False),
    ("voice", "stt_model", "small"),
    ("voice", "stt_child_cpu_seconds", 0),
    ("voice", "llm_streaming_enabled", True),
    ("memory", "auto_save_enabled", True),
    ("memory", "database", "memory.db"),
    ("files", "write_enabled", True),
    ("selfdev", "promotion_enabled", True),
    ("ventuno", "rpc_write_enabled", True),
    ("geniex_supervisor", "restart_enabled", True),
    ("camera", "enabled", True),
])
def test_any_staging_drift_cannot_silently_approve(
        tmp_path, section, key, value):
    profile = json.loads(stage.STAGE.read_text())
    profile[section][key] = value
    altered = tmp_path / "changed.json"
    altered.write_text(json.dumps(profile))
    result = stage.inspect(stage.SOURCE, altered)
    assert result["candidate_safe_by_contract"] is False
    assert result["real_audio_authorized"] is False


def test_unsafe_source_refused_even_with_safe_stage(tmp_path):
    profile = json.loads(stage.SOURCE.read_text())
    profile["voice"]["enabled"] = True
    source = tmp_path / "unsafe.json"
    source.write_text(json.dumps(profile))
    assert stage.inspect(source, stage.STAGE)["candidate_safe_by_contract"] is False
    with pytest.raises(ValueError):
        stage.candidate(profile)


def test_stage_symlink_and_bad_json_fail_closed(tmp_path):
    altered = tmp_path / "linked.json"
    altered.symlink_to(stage.STAGE)
    assert stage.inspect(stage.SOURCE, altered)["candidate_safe_by_contract"] is False
    altered.unlink()
    altered.write_text("{bad", encoding="utf-8")
    assert stage.inspect(stage.SOURCE, altered)["candidate_safe_by_contract"] is False


def test_status_is_sanitized_does_not_authorize_real_recording(capsys):
    assert stage.main() == 0
    text = capsys.readouterr().out
    assert text.startswith("MYAI_VOICE_STAGE_CONTRACT_JSON=")
    result = json.loads(text.partition("=")[2])
    assert result["real_audio_authorized"] is False
    assert result["libraries_installed"] is False
    assert result["test_database_created"] is False
    assert result["npu_inference_started"] is False
    assert "/home/arduino" not in text


def test_contract_does_not_resolve_to_default_runtime_paths():
    profile = json.loads(stage.STAGE.read_text())
    actual = _merge_settings(DEFAULT_SETTINGS, profile)
    assert actual["memory"]["database"] != "memory.db"
    for section, field in (
        ("runtime", "heartbeat_path"), ("health", "state_path"),
        ("error_logging", "path"), ("audit_logging", "path"),
        ("geniex_supervisor", "state_path"),
        ("stability_analysis", "log_path"),
    ):
        assert actual[section][field].startswith(stage.STAGING_PREFIX)
