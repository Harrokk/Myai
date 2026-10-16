"""Synthetic source-drift tests, never invoke a physical Actions workflow."""
import json

from scripts import ventuno_manual_actions_triage_gate as gate


def _manifest():
    return json.loads((gate.ROOT / gate.MANIFEST).read_text(encoding="utf-8"))


def test_current_repo_has_exactly_56_classified_manual_candidates():
    result = gate.reconcile()
    assert result["status"] == "all-56-source-triage-stable-not-authorized"
    assert result["source_triage_complete"] is True
    assert result["observed"] == 56
    assert result["quarantined_model_jobs_verified"] == 15
    assert result["production_deployment_authorized"] is False
    assert result["physical_tests_authorized"] is False
    assert result["main_merge_authorized"] is False


def test_missing_or_malformed_manifest_is_no_go(tmp_path):
    target = tmp_path / "manifest.json"
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False
    target.write_text("not json", encoding="utf-8")
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False
    target.unlink()
    target.symlink_to(gate.ROOT / gate.MANIFEST)
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False


def test_duplicate_unknown_or_reclassified_manual_workflow_is_no_go(tmp_path):
    doc = _manifest()
    target = tmp_path / "manifest.json"
    names = doc["groups"]["15 disabled model/GenieX/HTP jobs"]
    names[0] = names[1]
    target.write_text(json.dumps(doc), encoding="utf-8")
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False
    doc = _manifest()
    doc["groups"]["12 metadata, inventory or dry-run workflows"][0] = "unknown-new.yml"
    target.write_text(json.dumps(doc), encoding="utf-8")
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False
    doc = _manifest()
    doc["groups"]["15 disabled model/GenieX/HTP jobs"][0] = (
        doc["groups"]["12 metadata, inventory or dry-run workflows"][0]
    )
    target.write_text(json.dumps(doc), encoding="utf-8")
    assert gate.reconcile(manifest_path=target)["source_triage_complete"] is False


def test_release_or_physical_authorization_flags_never_accepted(tmp_path):
    target = tmp_path / "manifest.json"
    for key in ("release_authorized", "physical_test_authorized"):
        doc = _manifest()
        doc[key] = True
        target.write_text(json.dumps(doc), encoding="utf-8")
        assert gate.reconcile(manifest_path=target)["status"] == "blocked-source-triage-drift"


def test_new_unreviewed_manual_workflow_blocks_gate(monkeypatch):
    original = gate.workflows.inventory
    def fake(root, *, branch):
        report = original(root, branch=branch)
        report["risks"] = report["risks"] + [
            {"filename": "new-secret-model-action.yml", "manual_dispatch": True}
        ]
        return report
    monkeypatch.setattr(gate.workflows, "inventory", fake)
    result = gate.reconcile()
    assert result["new_unreviewed_count"] == 1
    assert result["source_triage_complete"] is False
    assert "new-secret-model-action.yml" in result["new_unreviewed_filenames"]


def test_existing_sensitive_workflow_becoming_disabled_or_reenabled_blocks(monkeypatch):
    original = gate.workflows.inventory
    def filtered(root, *, branch):
        report = original(root, branch=branch)
        report["risks"] = report["risks"][:-1]
        return report
    monkeypatch.setattr(gate.workflows, "inventory", filtered)
    report = gate.reconcile()
    assert report["source_triage_complete"] is False
    assert report["missing_from_scanner_count"] >= 1


def test_quarantine_must_be_verified_at_real_source_tree(monkeypatch):
    monkeypatch.setattr(gate.ten, "verify",
                        lambda root: {"confirmed_disabled": 9})
    assert gate.reconcile()["source_triage_complete"] is False


def test_current_source_inventory_cannot_auto_authorize_unsafe_main(monkeypatch):
    original = gate.workflows.inventory
    def fake(root, *, branch):
        report = original(root, branch=branch)
        report["candidate_automatic_clear"] = False
        report["status"] = "possible-automatic-effectful-workflow-no-go"
        return report
    monkeypatch.setattr(gate.workflows, "inventory", fake)
    assert gate.reconcile()["status"] == "blocked-source-triage-drift"
