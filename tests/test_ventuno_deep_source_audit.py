"""No hardware: structural audit assertions for the exact checkout."""
from pathlib import Path

from scripts import ventuno_deep_source_audit as scan


ROOT = Path(__file__).resolve().parents[1]


def test_every_tracked_file_was_counted_in_two_separate_passes():
    value = scan.audit(ROOT)
    logic = value["passes"]["logic"]
    security = value["passes"]["security"]
    assert logic["tracked_files_inspected"] >= 750
    assert logic["inventory"]["tracked_files"] >= 750
    assert logic["inventory"]["python_files"] == logic["inventory"]["python_valid"]
    assert logic["invalid_python_files"] == []
    assert logic["tool_name_count"] >= 50
    assert logic["tool_name_collisions"] == []
    assert security["inventory"]["workflow_files"] >= 140
    assert security["inventory"]["self_hosted_workflow_files"] >= 100
    assert value["actual_physical_tests_performed"] is False
    assert value["safe_to_deploy_automatically"] is False


def test_source_audit_does_not_assume_npu_or_voice_are_enabled():
    data = scan.audit(ROOT)["passes"]["security"]["ventuno_profile"]
    assert data["voice_enabled"] is False
    assert data["tts_enabled"] is False
    assert data["stt_model"] == "small"
    assert data["deployment_lock_required"] is False
    assert data["rpc_write_enabled"] is False


def test_risky_calls_explicitly_remain_visible_not_suppressed():
    security = scan.audit(ROOT)["passes"]["security"]
    assert {
        "file": "core/voice_stt_persistent.py",
        "line": 235,
        "call": "subprocess.Popen",
    } in security["production_sensitive_calls"]
    assert security["inventory"]["direct_requirements"] >= 10
    assert security["inventory"]["requirements_without_hash"] >= 10
    assert security["self_hosted_push_hardware_candidates"]


def test_structural_scan_only_returns_sanitized_static_evidence():
    report = scan.audit(ROOT)
    import json
    text = json.dumps(report)
    assert "access_token" not in text
    assert "HF_HUB_TOKEN" not in text
    assert "PRIVATE_AUDIO" not in text
    assert report["status"].startswith("source-audit")
