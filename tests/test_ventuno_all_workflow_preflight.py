"""Risk inventories cannot authorize physical hardware workflows."""
from scripts import ventuno_all_workflow_preflight as mod


def test_current_repository_audits_all_workflows_without_running_any():
    result = mod.inventory()
    assert result["counts"]["total_workflows"] >= 140
    assert result["hardware_authorized"] is False
    assert result["manual_workflows_are_not_approved_by_this_audit"] is True
    assert result["dynamic_workflow_expressions_certified_safe"] is False


def test_unrestricted_self_hosted_push_audio_action_fails_closed(tmp_path):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / "unsafe.yml").write_text(
        "name: bad\non:\n  push:\njobs:\n"
        "  dangerous:\n    runs-on: [self-hosted, ARM64]\n"
        "    steps:\n      - run: arecord -d 3 /tmp/private.wav\n"
    )
    result = mod.inventory(tmp_path)
    assert result["status"] == "blocked-possible-automatic-hardware-triggers"
    assert result["counts"]["current_branch_automatic_risks"] == 1
    assert result["hardware_authorized"] is False


def test_old_branch_specific_manual_job_not_automatically_approved(tmp_path):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / "old.yml").write_text(
        "name: old\non:\n  push:\n"
        "    branches: [dev/obsolete-one-shot]\n"
        "  workflow_dispatch:\njobs:\n"
        "  dangerous:\n    runs-on: [self-hosted, ARM64]\n"
        "    steps:\n      - run: aplay -q /tmp/sound.wav\n"
    )
    result = mod.inventory(tmp_path)
    assert result["counts"]["manual_hardware_candidates"] == 1
    assert result["counts"]["current_branch_automatic_risks"] == 0
    assert result["hardware_authorized"] is False


def test_risky_comment_is_not_equivalent_to_ability_to_launch_audio(tmp_path):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / "notes.yml").write_text(
        "name: read-only\non:\n  push:\n"
        "    branches: [dev/elsewhere]\n"
        "# command formerly used arecord and aplay\n"
        "jobs:\n  audit:\n    runs-on: ubuntu-24.04\n"
        "    steps:\n      - run: echo safe\n"
    )
    result = mod.inventory(tmp_path)
    assert result["counts"]["hardware_candidates"] == 0


def test_unreadable_source_and_symlink_block_review(tmp_path):
    folder = tmp_path / ".github" / "workflows"
    folder.mkdir(parents=True)
    (folder / "probe.yml").symlink_to(tmp_path / "other.yml")
    assert mod.inventory(tmp_path)["status"] == "blocked-unreadable-actions-source"
