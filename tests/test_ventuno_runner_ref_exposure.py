"""No GitHub API calls, dispatches, runner signals, filesystem mutations or hardware."""
import json
from pathlib import Path

import pytest

from scripts import ventuno_runner_ref_exposure as gate


def test_source_branch_inventory_remains_explicit_no_go():
    info = gate.inspect()
    assert info["source_inventory_complete"] is True
    assert info["workflow_files_scanned"] >= 170
    assert info["historical_exposure_snapshots_count"] == 5
    assert info["possible_self_hosted_workflow_count"] > 0
    assert info["possible_auto_or_indirect_workflow_count"] > 0
    assert info["runner_exposure_closed"] is False
    assert info["runner_api_group_permissions_verified"] is False
    assert info["historical_branches_live_runner_access_verified"] is False
    assert info["production_deployment_authorized"] is False
    assert info["main_merge_authorized"] is False
    assert info["github_actions_job_execution_was_attempted"] is False
    assert gate.main(["--strict-production"]) == 2


@pytest.mark.parametrize("selector", [
    "[self-hosted, Linux, ARM64, ventuno-q]",
    "self-hosted",
    "${{ fromJSON(needs.prepare.outputs.labels) }}",
    "${{ matrix.runner }}",
    "",
    "[self-hosted, Linux, ARM64]",
    "group: privileged-runner",
    "[ubuntu-latest, self-hosted]",
])
def test_unsafe_or_dynamic_runner_selectors_never_look_hosted_only(selector):
    yml = "on:\n  push:\njobs:\n  test:\n    runs-on: " + selector + "\n"
    info = gate.classify_workflow(yml)
    assert info["potential_self_hosted_or_unknown_selectors"] == 1
    assert info["trigger_hint"] == "automatic-or-indirect-source-hint"
    assert info["runner_group_policy_verified"] is False


@pytest.mark.parametrize("hosted", [
    "ubuntu-24.04-arm", "ubuntu-24.04", "ubuntu-22.04-arm", "ubuntu-latest"
])
def test_static_hosted_labels_are_distinct_from_source_only_release_approval(hosted):
    source = "on:\n  push:\njobs:\n  test:\n    runs-on: " + hosted + "\n"
    info = gate.classify_workflow(source)
    assert info["static_hosted_selector_count"] == 1
    assert info["potential_self_hosted_or_unknown_selectors"] == 0
    assert info["runner_group_policy_verified"] is False
    assert info["full_github_actions_yaml_semantics_verified"] is False


@pytest.mark.parametrize("trigger", [
    "  push:\n    branches: [dev/old]\n",
    "  schedule:\n    - cron: '0 12 * * *'\n",
    "  workflow_run:\n    workflows: [Build]\n",
    "  repository_dispatch:\n",
    "  workflow_call:\n",
])
def test_old_branch_or_indirect_trigger_is_still_automatic_exposure(trigger):
    yml = "on:\n" + trigger + "jobs:\n  audit:\n    runs-on: self-hosted\n"
    info = gate.classify_workflow(yml)
    assert info["trigger_hint"] == "automatic-or-indirect-source-hint"


def test_manual_only_is_hint_not_authorization():
    info = gate.classify_workflow(
        "on:\n  workflow_dispatch:\njobs:\n  test:\n    runs-on: self-hosted\n"
    )
    assert info["trigger_hint"] == "manual-only-source-hint"
    assert info["potential_self_hosted_or_unknown_selectors"] == 1
    assert info["runner_group_policy_verified"] is False


def test_inline_or_malformed_events_never_clear_automatic_risk():
    for s in ("on: [push, workflow_dispatch]\n", "on: push\n", "no triggers\n"):
        info = gate.classify_workflow(s + "jobs:\n  audit:\n    runs-on: self-hosted\n")
        assert info["trigger_hint"] == "unknown-event-shape"
        assert info["potential_self_hosted_or_unknown_selectors"] == 1


def test_reusable_nested_workflow_without_runs_on_is_opaque():
    info = gate.classify_workflow(
        "on:\n  push:\njobs:\n  call:\n"
        "    uses: owner/repo/.github/workflows/unsafe.yml@main\n"
    )
    assert info["potential_self_hosted_or_unknown_selectors"] == 1


def _fixture(tmp_path):
    path = tmp_path / gate.EVIDENCE_PATH
    path.parent.mkdir(parents=True)
    path.write_text((gate.ROOT / gate.EVIDENCE_PATH).read_text(encoding="utf-8"),
                    encoding="utf-8")
    workflows = tmp_path / gate.WORKFLOWS
    workflows.mkdir(parents=True)
    (workflows / "unsafe.yml").write_text(
        "on:\n  push:\n    branches: [dev/old]\njobs:\n"
        "  test:\n    runs-on: [self-hosted, Linux, ARM64, ventuno-q]\n",
        encoding="utf-8")
    (workflows / "safe.yml").write_text(
        "on:\n  push:\njobs:\n  test:\n    runs-on: ubuntu-24.04-arm\n",
        encoding="utf-8")
    return tmp_path


def test_tiny_fixture_counts_exposure_without_closing_runner_gate(tmp_path):
    root = _fixture(tmp_path)
    info = gate.inspect(root)
    assert info["source_inventory_complete"] is True
    assert info["workflow_files_scanned"] == 2
    assert info["possible_self_hosted_workflow_count"] == 1
    assert info["possible_auto_or_indirect_workflow_count"] == 1
    assert info["runner_exposure_closed"] is False


@pytest.mark.parametrize("mutator", ["delete", "wrong-sha", "claim-access", "erase-entry", "duplicate"])
def test_historical_evidence_cannot_be_silently_modified_to_clear_gate(tmp_path, mutator):
    root = _fixture(tmp_path)
    path = root / gate.EVIDENCE_PATH
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if mutator == "delete":
        path.unlink()
    else:
        if mutator == "wrong-sha":
            manifest["snapshots"][0]["blob_sha"] = "0" * 40
        if mutator == "claim-access":
            manifest["production_runner_access_policy_verified"] = True
        if mutator == "erase-entry":
            manifest["snapshots"].pop()
        if mutator == "duplicate":
            manifest["snapshots"][-1] = manifest["snapshots"][0]
        path.write_text(json.dumps(manifest), encoding="utf-8")
    info = gate.inspect(root)
    assert info["source_inventory_complete"] is False
    assert info["runner_exposure_closed"] is False
    assert info["production_deployment_authorized"] is False


def test_symlinked_historical_workflow_incomplete(tmp_path):
    root = _fixture(tmp_path)
    file = root / gate.WORKFLOWS / "unsafe.yml"
    out = tmp_path / "target"
    out.write_text(file.read_text(encoding="utf-8"), encoding="utf-8")
    file.unlink()
    file.symlink_to(out)
    info = gate.inspect(root)
    assert info["source_inventory_complete"] is False
    assert info["production_deployment_authorized"] is False
