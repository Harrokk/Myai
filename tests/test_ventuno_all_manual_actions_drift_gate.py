"""Source-only tests for complete 103 manual workflow baseline."""
import json

from scripts import ventuno_all_manual_actions_drift_gate as allgate


def _baseline():
    return json.loads((allgate.ROOT / allgate.MANIFEST).read_text(encoding="utf-8"))


def test_all_103_manual_workflows_accounted_and_no_release_authorized():
    status = allgate.inspect()
    assert status["status"] == "all-103-manual-action-names-accounted-no-release"
    assert status["observed_manual_count"] == 103
    assert status["keyword_sensitive_manual_count"] == 56
    assert status["additional_non_keyword_manual_count"] == 47
    assert status["manual_workflow_source_inventory_complete"] is True
    assert status["indirect_script_and_action_security_certified"] is False
    assert status["main_merge_authorized"] is False
    assert status["physical_tests_authorized"] is False


def test_unexpected_unflagged_manual_job_never_passes(monkeypatch):
    original = allgate.review.inventory
    def with_new(root, *, branch):
        report = original(root, branch=branch)
        report["all_manual_workflow_filenames"] += ["manual-bad-uses.yml"]
        return report
    monkeypatch.setattr(allgate.review, "inventory", with_new)
    result = allgate.inspect()
    assert result["status"] == "blocked-unaccounted-manual-action"
    assert "manual-bad-uses.yml" in result["new_manual_filenames"]


def test_missing_manual_job_is_detected(monkeypatch):
    original = allgate.review.inventory
    def missing(root, *, branch):
        report = original(root, branch=branch)
        report["all_manual_workflow_filenames"] = report["all_manual_workflow_filenames"][:-1]
        return report
    monkeypatch.setattr(allgate.review, "inventory", missing)
    assert allgate.inspect()["status"] == "blocked-unaccounted-manual-action"


def test_manifest_duplicate_and_invalid_authorizations_are_denied(tmp_path):
    path = tmp_path / "manual.json"
    data = _baseline()
    data["all_manual_workflow_filenames"][0] = data["all_manual_workflow_filenames"][1]
    path.write_text(json.dumps(data), encoding="utf-8")
    assert allgate.inspect(manifest_path=path)["status"] == "blocked-unaccounted-manual-action"
    for key in ("physical_authorized", "merge_authorized", "production_deploy_authorized"):
        data = _baseline()
        data[key] = True
        path.write_text(json.dumps(data), encoding="utf-8")
        assert allgate.inspect(manifest_path=path)["status"] == "blocked-unaccounted-manual-action"


def test_wrong_47_file_subset_or_unknown_trigger_blocks(tmp_path, monkeypatch):
    path = tmp_path / "manual.json"
    data = _baseline()
    data["non_keyword_manual_workflow_filenames"][0] = (
        "ventuno-diagnostics.yml"
    )
    path.write_text(json.dumps(data), encoding="utf-8")
    assert allgate.inspect(manifest_path=path)["status"] == "blocked-unaccounted-manual-action"

    original = allgate.review.inventory
    def unknown(root, *, branch):
        report = original(root, branch=branch)
        report["unknown_event_workflow_filenames"] = ["not-parsed.yml"]
        return report
    monkeypatch.setattr(allgate.review, "inventory", unknown)
    assert allgate.inspect()["status"] == "blocked-unaccounted-manual-action"


def test_missing_file_and_symlinked_manifest_fail_closed(tmp_path):
    target = tmp_path / "missing.json"
    assert allgate.inspect(manifest_path=target)["status"] == "blocked-unaccounted-manual-action"
    target.symlink_to(allgate.ROOT / allgate.MANIFEST)
    assert allgate.inspect(manifest_path=target)["status"] == "blocked-unaccounted-manual-action"
