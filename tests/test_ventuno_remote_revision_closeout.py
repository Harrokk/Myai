"""Pure repository-source tests; do not run Actions, audio or systemd."""
import json

from scripts import ventuno_manual_workflow_source_identity as ident
from scripts import ventuno_remote_revision_closeout as review


def test_git_blob_oid_matches_standard_git_blob_payload():
    assert ident._blob_oid(b"hello\n") == "ce013625030ba8dba906f756967f9e9ca394464a"


def test_prior_manual_review_baseline_blocks_intentionally_changed_ci_workflow():
    # The original 2026-10-16 evidence is immutable. Rehosting tests.yml
    # must keep the earlier 103-file closeout FAIL-CLOSED until a *new*
    # manual approval produces separate, dated review evidence.
    report = ident.check()
    assert report["status"] == "blocked-manual-workflow-source-changed"
    assert report["matched"] == 102
    assert report["unverified_count"] == 1
    assert report["unverified_filenames"] == ["tests.yml"]
    assert report["manifest_valid"] is True
    assert report["third_party_actions_verified"] is False
    assert report["production_release_authorized"] is False


def test_changed_source_blob_is_blocked(tmp_path):
    source = ident.ROOT / ident.MANIFEST
    data = json.loads(source.read_text(encoding="utf-8"))
    first = next(iter(sorted(data["manual_workflow_git_blob_oids"])))
    data["manual_workflow_git_blob_oids"][first] = "0" * 40
    target = tmp_path / "changed.json"
    target.write_text(json.dumps(data), encoding="utf-8")
    result = ident.check(manifest_path=target)
    assert result["status"] == "blocked-manual-workflow-source-changed"
    assert first in result["unverified_filenames"]
    # tests.yml was already flagged by the frozen earlier baseline.
    assert result["matched"] == 101
    assert "tests.yml" in result["unverified_filenames"]


def test_invalid_manifest_symlink_or_permission_claim_is_denied(tmp_path):
    target = tmp_path / "manifest.json"
    assert ident.check(manifest_path=target)["manifest_valid"] is False
    target.symlink_to(ident.ROOT / ident.MANIFEST)
    assert ident.check(manifest_path=target)["manifest_valid"] is False
    target.unlink()
    data = json.loads((ident.ROOT / ident.MANIFEST).read_text(encoding="utf-8"))
    data["production_release_authorized"] = True
    target.write_text(json.dumps(data), encoding="utf-8")
    assert ident.check(manifest_path=target)["status"] == "blocked-manual-workflow-source-changed"


def test_prior_remote_closeout_stays_blocked_after_ci_workflow_migration():
    report = review.closeout()
    assert report["status"] == "blocked-source-revision-incomplete"
    assert report["remote_source_gates_passed"] is False
    assert report["checks"]["all_103_manual_workflow_contents_unchanged"] is False
    assert report["all_hardware_revision_gates_closed"] is False
    assert report["main_merge_authorized"] is False
    assert report["production_deployment_authorized"] is False
    assert report["source_checks_are_not_manual_line_by_line_certification"] is True


def test_closeout_denies_any_missing_source_gate(monkeypatch):
    monkeypatch.setattr(
        review.timers, "check",
        lambda root: {"status": "blocked-board-timer-job-still-reachable"}
    )
    report = review.closeout()
    assert report["status"] == "blocked-source-revision-incomplete"
    assert report["checks"]["two_board_timer_jobs_inert"] is False
    assert report["main_merge_authorized"] is False


def test_closeout_denies_disappearing_manual_content_evidence(monkeypatch):
    monkeypatch.setattr(
        review.identity, "check",
        lambda root: {"status": "blocked-manual-workflow-source-changed"}
    )
    result = review.closeout()
    assert result["remote_source_gates_passed"] is False
    assert result["production_deployment_authorized"] is False
