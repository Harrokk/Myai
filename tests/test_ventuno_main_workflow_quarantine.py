"""Synthetic assurance that former main-only jobs cannot touch VENTUNO."""
import json

from scripts import ventuno_main_workflow_quarantine as gate


def test_exact_four_main_only_workflows_are_inert():
    report = gate.classify()
    assert report["status"] == "four-main-workflows-quarantined"
    assert report["quarantined_workflows"] == report["expected_workflows"] == 4
    assert report["hardware_execution_authorized"] is False
    assert report["main_modified"] is False


def test_missing_and_unsafe_workflow_fails_closed(tmp_path):
    root = tmp_path
    (root / ".github" / "workflows").mkdir(parents=True)
    for name in gate.NAMES:
        source = gate.ROOT / ".github" / "workflows" / name
        (root / ".github" / "workflows" / name).write_bytes(source.read_bytes())
    assert gate.classify(root)["quarantine_verified"]
    file = root / ".github" / "workflows" / gate.NAMES[0]
    file.write_text(file.read_text() + "\n  push:\n    branches: [main]\n")
    assert not gate.classify(root)["quarantine_verified"]
    file.unlink()
    assert not gate.classify(root)["quarantine_verified"]


def test_only_fixed_non_sensitive_aggregate_results():
    assert set(gate.classify()) == {
        "status", "quarantined_workflows", "expected_workflows",
        "quarantine_verified", "live_production_workflow_run_attempted",
        "main_modified", "hardware_execution_authorized",
    }
    assert "secret" not in json.dumps(gate.classify())
