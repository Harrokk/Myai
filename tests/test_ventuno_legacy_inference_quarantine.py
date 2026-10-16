"""Fake GitHub workflow sources; no jobs, audio or inference are executed."""
from scripts import ventuno_legacy_inference_quarantine as check


def _write_all(root, *, wrong=None):
    folder = root / ".github/workflows"
    folder.mkdir(parents=True, exist_ok=True)
    for filename, job in check.DISABLED.items():
        condition = "if: false" if filename != wrong else "if: true"
        (folder / filename).write_text(
            "name: historical one-shot\non:\n  workflow_dispatch:\n"
            "jobs:\n  " + job + ":\n    # ARCHIVED - NO HARDWARE EXECUTION\n"
            "    " + condition + "\n    runs-on: [self-hosted, ARM64]\n"
            "    steps:\n      - run: echo not-run\n",
            encoding="utf-8",
        )


def test_repo_legacy_jobs_are_inert():
    result = check.verify()
    assert result["status"] == "four-legacy-device-jobs-inert"
    assert result["confirmed_disabled"] == 4
    assert result["device_used"] is False
    assert result["release_authorized"] is False


def test_all_disabled_synthetic_jobs_pass(tmp_path):
    _write_all(tmp_path)
    assert check.verify(tmp_path)["confirmed_disabled"] == 4


def test_active_job_denied_even_with_disabled_inner_step(tmp_path):
    filename = "ventuno-diagnostics.yml"
    _write_all(tmp_path, wrong=filename)
    path = tmp_path / ".github/workflows" / filename
    path.write_text(path.read_text() + "        if: false\n")
    result = check.verify(tmp_path)
    assert result["status"] == "blocked-legacy-device-job-enabled"
    assert result["confirmed_disabled"] == 3


def test_missing_file_symlink_and_duplicate_job_are_denied(tmp_path):
    _write_all(tmp_path)
    filename = "ventuno-diagnostics.yml"
    path = tmp_path / ".github/workflows" / filename
    path.unlink()
    assert check.verify(tmp_path)["confirmed_disabled"] == 3
    path.symlink_to(tmp_path / "elsewhere.yml")
    assert check.verify(tmp_path)["confirmed_disabled"] == 3
    path.unlink()
    _write_all(tmp_path)
    path.write_text(path.read_text() + "  diagnostics:\n    if: false\n")
    assert check.verify(tmp_path)["confirmed_disabled"] == 3
