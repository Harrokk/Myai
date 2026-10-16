"""Synthetic source tests for five reviewed manually-dispatchable model jobs."""
from scripts import ventuno_five_real_model_job_quarantine as gate


def _fixture(root, *, live=False):
    work = root / ".github/workflows"
    work.mkdir(parents=True, exist_ok=True)
    for filename, (blocked, jobs) in gate.REQUIRED.items():
        text = ["name: old source-only", "on:", "  workflow_dispatch:", "jobs:"]
        for job in jobs:
            text += ["  " + job + ":"]
            if job == blocked:
                text += ["    # archived because real model is unreviewed",
                         "    if: true" if live else "    if: false"]
            text += [
                "    runs-on: ubuntu-24.04" if job == "synthetic-safety"
                else "    runs-on: [self-hosted, Linux, ARM64, ventuno-q]",
                "    steps:", "      - run: echo synthetic-fixture",
            ]
        (work / filename).write_text("\n".join(text) + "\n", encoding="utf-8")
    return work


def test_real_repo_five_jobs_inert_without_device_access():
    report = gate.verify()
    assert report["status"] == "five-real-inference-jobs-quarantined"
    assert report["checked_files"] == 5
    assert report["confirmed_inert"] == 5
    assert report["real_model_inference_performed"] is False
    assert report["release_authorized"] is False


def test_synthetic_safe_and_enabled_fail_closed(tmp_path):
    _fixture(tmp_path)
    assert gate.verify(tmp_path)["confirmed_inert"] == 5
    _fixture(tmp_path, live=True)
    assert gate.verify(tmp_path)["confirmed_inert"] == 0


def test_missing_and_symlinked_files_never_clear(tmp_path):
    folder = _fixture(tmp_path)
    file = folder / "ventuno-public-dynamic-transcript.yml"
    file.unlink()
    assert gate.verify(tmp_path)["confirmed_inert"] == 4
    file.symlink_to(tmp_path / "somewhere.yml")
    assert gate.verify(tmp_path)["confirmed_inert"] == 4


def test_extra_unknown_job_is_blocked(tmp_path):
    folder = _fixture(tmp_path)
    file = folder / "ventuno-piper-alma-swedish-stt.yml"
    file.write_text(file.read_text() + "  surprise:\n    runs-on: [self-hosted]\n")
    assert gate.verify(tmp_path)["confirmed_inert"] == 4


def test_mixed_workflow_keeps_x86_mocked_sibling(tmp_path):
    folder = _fixture(tmp_path)
    file = folder / "ventuno-existing-geniex-one-shot-check.yml"
    source = file.read_text()
    assert gate.verify(tmp_path)["confirmed_inert"] == 5
    file.write_text(source.replace("runs-on: ubuntu-24.04",
                                   "runs-on: [self-hosted, Linux, ARM64]"))
    assert gate.verify(tmp_path)["confirmed_inert"] == 4
    file.write_text(source.replace(
        "  synthetic-safety:\n    runs-on:", "  synthetic-safety:\n    if: false\n    runs-on:"
    ))
    assert gate.verify(tmp_path)["confirmed_inert"] == 4


def test_step_level_false_does_not_disable_job(tmp_path):
    folder = _fixture(tmp_path, live=True)
    file = folder / "ventuno-synthetic-swedish-question-stt.yml"
    file.write_text(file.read_text() + "      - if: false\n        run: echo inner\n")
    assert gate.verify(tmp_path)["status"] == "blocked-real-inference-job-reachable"
