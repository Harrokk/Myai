"""Source-only workflow inventory regression; never run a workflow."""
from pathlib import Path

from scripts import ventuno_workflow_release_review as review


def _fixture(tmp_path, monkeypatch, files):
    directory = tmp_path / ".github" / "workflows"
    directory.mkdir(parents=True)
    for name, data in files.items():
        (directory / name).write_text(data, encoding="utf-8")
    monkeypatch.setattr(
        review, "_tracked_workflows",
        lambda root: [".github/workflows/" + n for n in sorted(files)]
    )
    return tmp_path


def test_unsafe_push_without_branch_restriction_is_no_go(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "unsafe.yml": "name: live\non:\n  push:\njobs:\n  mic:\n"
                      "    runs-on: [self-hosted, ARM64]\n"
                      "    steps:\n      - run: arecord -d 3 /tmp/a.wav\n",
    })
    result = review.inventory(root)
    assert result["counts"]["automatic_sensitive_candidates"] == 1
    assert review.exit_code(result) == 2
    assert result["physical_tests_authorized"] is False


def test_old_branch_is_not_auto_authorized_and_manual_is_no_go(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "old.yml": "name: old\non:\n  push:\n"
                   "    branches: [dev/old-experiment]\n"
                   "  workflow_dispatch:\njobs:\n"
                   "  audio:\n    runs-on: [self-hosted]\n"
                   "    steps:\n      - run: aplay -q /tmp/a.wav\n",
    })
    result = review.inventory(root)
    assert result["candidate_automatic_clear"] is True
    assert result["counts"]["manual_sensitive_candidates"] == 1
    assert result["release_ready"] is False
    assert review.exit_code(result) == 0
    assert review.exit_code(result, release=True) == 2


def test_multiline_and_wildcard_push_are_conservative(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "case.yml": "name: audio\non:\n  push:\n    branches:\n"
                    "      - dev/old-experiment\njobs:\n  record:\n"
                    "    runs-on: [self-hosted]\n    steps:\n"
                    "      - run: arecord -d 1 /tmp/a.wav\n"
    })
    assert review.inventory(root)["candidate_automatic_clear"] is True
    path = root / ".github/workflows/case.yml"
    path.write_text(path.read_text().replace("dev/old-experiment", "dev/*"))
    assert review.inventory(root)["candidate_automatic_clear"] is False
    path.write_text(path.read_text().replace("dev/*", review.CURRENT_BRANCH))
    assert review.inventory(root)["candidate_automatic_clear"] is False


def test_schedule_effectful_is_blocked_even_without_push(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "daily.yml": "name: dangerous\non:\n  schedule:\n"
                     "    - cron: '0 6 * * *'\njobs:\n"
                     "  run:\n    runs-on: ubuntu-24.04\n"
                     "    steps:\n      - run: qnn-net-run --backend /tmp/lib.so\n",
    })
    assert review.inventory(root)["counts"]["automatic_sensitive_candidates"] == 1


def test_comment_only_mentions_do_not_create_false_positive(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "notes.yml": "name: text\non:\n  push:\n"
                     "    branches: [dev/other]\n# arecord geniex aplay\n"
                     "jobs:\n  checks:\n    runs-on: ubuntu-24.04\n"
                     "    steps:\n      - run: echo source-only\n"
    })
    result = review.inventory(root)
    assert result["counts"]["sensitive_candidates"] == 0
    assert review.exit_code(result) == 0
    assert review.exit_code(result, release=True) == 2


def test_missing_symlink_and_unreadable_fail_closed(tmp_path, monkeypatch):
    root = _fixture(tmp_path, monkeypatch, {
        "link.yml": "name: safe\non:\n  workflow_dispatch:\njobs:\n"
                    "  check:\n    runs-on: ubuntu-24.04\n"
    })
    file = root / ".github/workflows/link.yml"
    file.unlink()
    file.symlink_to(tmp_path / "elsewhere.yml")
    report = review.inventory(root)
    assert report["status"] == "incomplete-no-go"
    assert review.exit_code(report) == 2
    assert report["approval_proven"] is False


def test_empty_or_malformed_result_cannot_pass_release():
    assert review.exit_code(None) == 2
    assert review.exit_code({"status": "incomplete-no-go"}) == 2
    assert review.exit_code({"status": "inventory-complete-not-release-authorized",
                             "candidate_automatic_clear": False}) == 2
    assert review.exit_code({"status": "inventory-complete-not-release-authorized",
                             "candidate_automatic_clear": True}, release=True) == 2


def test_cli_release_flag_rejects_even_synthetically_clear_inventory(monkeypatch, capsys):
    fake = {"status": "inventory-complete-not-release-authorized",
            "candidate_automatic_clear": True, "release_ready": False}
    monkeypatch.setattr(review, "inventory", lambda branch=None: fake)
    assert review.main([]) == 0
    assert review.main(["--release-gate"]) == 2
    assert "MYAI_WORKFLOW_REVIEW_JSON=" in capsys.readouterr().out


def test_current_repo_must_list_every_tracked_workflow():
    result = review.inventory()
    assert result["counts"]["total_workflows"] >= 150
    assert result["counts"]["sensitive_candidates"] >= 1
    assert result["release_ready"] is False
    assert result["approval_proven"] is False
    assert result["physical_tests_authorized"] is False
    assert result["dynamic_yaml_actions_expressions_verified"] is False


def test_ci_branch_is_passed_to_inventory_not_fixed_old_branch(monkeypatch):
    seen = []
    monkeypatch.setenv("GITHUB_REF_NAME", "dev/review-new-branch")
    def fake(*, branch):
        seen.append(branch)
        return {"status": "inventory-complete-not-release-authorized",
                "candidate_automatic_clear": True}
    monkeypatch.setattr(review, "inventory", fake)
    assert review.main([]) == 0
    assert seen == ["dev/review-new-branch"]
    assert review.main(["--branch", "dev/explicit"]) == 0
    assert seen[-1] == "dev/explicit"
