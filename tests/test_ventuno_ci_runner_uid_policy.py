"""Non-installing source-only security policy for a future CI runner UID."""
from pathlib import Path

import pytest

from scripts import ventuno_ci_runner_uid_policy as policy


def test_checked_in_runner_template_is_inert_and_fails_production_closed():
    report = policy.inspect()
    assert report["candidate_unit_policy_valid"] is True
    assert report["status"] == "isolated-runner-template-reviewed-production-no-go"
    assert report["workflow_files_scanned"] >= 170
    assert report["direct_self_hosted_runner_workflows"] > 0
    assert report["candidate_unit_is_inert_example_only"] is True
    assert report["live_runner_uid_and_groups_verified"] is False
    assert report["live_source_and_secret_acl_verified"] is False
    assert report["old_trigger_branches_and_runner_group_policy_verified"] is False
    assert report["production_runner_service_reconfigured"] is False
    assert report["actual_privilege_separation_proven"] is False
    assert report["hardware_access_authorized"] is False
    assert report["main_merge_authorized"] is False
    assert report["production_deployment_authorized"] is False
    assert "ventuno" not in policy.SERVICE_FIELDS["User"]


@pytest.mark.parametrize("old,new", [
    ("User=myai-ci", "User=arduino"),
    ("User=myai-ci", "User=root"),
    ("Group=myai-ci", "Group=arduino"),
    ("ProtectHome=yes", "ProtectHome=no"),
    ("ProtectSystem=strict", "ProtectSystem=full"),
    ("NoNewPrivileges=yes", "NoNewPrivileges=no"),
    ("PrivateDevices=yes", "PrivateDevices=no"),
    ("PrivateTmp=yes", "PrivateTmp=no"),
    ("UMask=0077", "UMask=0022"),
    ("Restart=no", "Restart=always"),
    ("StateDirectory=myai-ci-runner", "StateDirectory=MyAI"),
    ("ExecStart=/var/lib/myai-ci-runner/runsvc.sh",
     "ExecStart=/home/arduino/actions-runner/runsvc.sh"),
    ("CapabilityBoundingSet=", "CapabilityBoundingSet=CAP_DAC_OVERRIDE"),
    ("AmbientCapabilities=", "AmbientCapabilities=CAP_SYS_ADMIN"),
])
def test_unsafe_systemd_unit_changes_are_rejected(old, new):
    source = (policy.ROOT / policy.CANDIDATE).read_text(encoding="utf-8")
    assert source.count(old) == 1
    assert not policy.validate_candidate_text(source.replace(old, new))


@pytest.mark.parametrize("extra", [
    "\n[Install]\nWantedBy=multi-user.target\n",
    "\n[Service]\nUser=root\n",
    "\nExecStartPre=/bin/sh -c 'echo unsafe'\n",
    "\nReadWritePaths=/home/arduino/MyAI\n",
    "\nSupplementaryGroups=arduino\n",
    "\nEnvironment=MYAI_OVERRIDE=1\n",
    "\nUser=arduino\n",
])
def test_surprise_systemd_sections_or_duplicated_settings_are_rejected(extra):
    source = (policy.ROOT / policy.CANDIDATE).read_text(encoding="utf-8")
    assert not policy.validate_candidate_text(source + extra)


def make_root(tmp_path):
    target = tmp_path / policy.CANDIDATE
    target.parent.mkdir(parents=True)
    target.write_text((policy.ROOT / policy.CANDIDATE).read_text(), encoding="utf-8")
    directory = tmp_path / ".github" / "workflows"
    directory.mkdir(parents=True)
    (directory / "hosted.yml").write_text(
        "name: hosted\non:\n  push:\njobs:\n  test:\n"
        "    runs-on: ubuntu-24.04-arm\n", encoding="utf-8",
    )
    (directory / "selfhosted.yml").write_text(
        "name: legacy\non:\n  push:\njobs:\n  test:\n"
        "    runs-on: [self-hosted, Linux, ARM64, ventuno-q]\n", encoding="utf-8",
    )
    return tmp_path


def test_synthetic_inventory_counts_direct_unreviewed_selfhosted_jobs(tmp_path):
    root = make_root(tmp_path)
    outcome = policy.inspect(root)
    assert outcome["candidate_unit_policy_valid"] is True
    assert outcome["workflow_files_scanned"] == 2
    assert outcome["direct_self_hosted_runner_workflows"] == 1
    assert outcome["direct_self_hosted_workflow_examples"] == ["selfhosted.yml"]
    assert outcome["production_deployment_authorized"] is False


def test_missing_or_linked_template_fails_closed(tmp_path):
    root = make_root(tmp_path)
    candidate = root / policy.CANDIDATE
    candidate.unlink()
    assert policy.inspect(root)["candidate_unit_policy_valid"] is False
    external = tmp_path / "outside-unit"
    external.write_text((policy.ROOT / policy.CANDIDATE).read_text())
    candidate.symlink_to(external)
    assert policy.inspect(root)["candidate_unit_policy_valid"] is False


def test_symlinked_workflow_fails_closed(tmp_path):
    root = make_root(tmp_path)
    source = root / ".github/workflows/hosted.yml"
    copy = tmp_path / "outside.yml"
    copy.write_text(source.read_text())
    source.unlink()
    source.symlink_to(copy)
    outcome = policy.inspect(root)
    assert outcome["candidate_unit_policy_valid"] is False
    assert outcome["production_deployment_authorized"] is False
