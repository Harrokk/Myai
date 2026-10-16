"""Synthetic job-map tests: no timer or service is started."""
from scripts import ventuno_board_timer_quarantine as mod


def _files(root, *, enabled=False):
    folder = root / ".github/workflows"
    folder.mkdir(parents=True, exist_ok=True)
    for file, (board, jobs, hosted) in mod.JOBS.items():
        lines = ["name: old canary", "on:", "  workflow_dispatch:", "jobs:"]
        for job in jobs:
            lines.append("  " + job + ":")
            if job == board:
                lines.extend(["    # DRAFT physical gate",
                              "    if: true" if enabled else "    if: false",
                              "    runs-on: [self-hosted, Linux, ARM64]"])
            else:
                lines.append("    runs-on: ubuntu-24.04")
            lines.extend(["    steps:", "      - run: echo fixture"])
        (folder / file).write_text("\n".join(lines) + "\n")
    return folder


def test_checked_in_board_timer_jobs_are_inert():
    r = mod.check()
    assert r["status"] == "two-board-timer-jobs-inert"
    assert r["disabled_verified"] == 2
    assert r["actual_timers_exercised"] is False
    assert r["out_of_band_recovery_verified"] is False
    assert r["physical_test_authorized"] is False


def test_reenabled_timer_job_must_fail(tmp_path):
    _files(tmp_path)
    assert mod.check(tmp_path)["disabled_verified"] == 2
    _files(tmp_path, enabled=True)
    assert mod.check(tmp_path)["disabled_verified"] == 0


def test_missing_linked_duplicate_or_renamed_job_must_fail(tmp_path):
    folder = _files(tmp_path)
    f = folder / "ventuno-htp-local-recovery-canary.yml"
    f.unlink()
    assert mod.check(tmp_path)["disabled_verified"] == 1
    f.symlink_to(tmp_path / "outside.yml")
    assert mod.check(tmp_path)["disabled_verified"] == 1
    f.unlink()
    _files(tmp_path)
    f.write_text(f.read_text() + "  unreviewed-live:\n    runs-on: [self-hosted]\n")
    assert mod.check(tmp_path)["disabled_verified"] == 1


def test_hosted_synthetic_job_must_remain_available(tmp_path):
    folder = _files(tmp_path)
    f = folder / "ventuno-system-manager-timer-canary.yml"
    f.write_text(f.read_text().replace(
        "  mock-safety:\n    runs-on: ubuntu-24.04",
        "  mock-safety:\n    if: false\n    runs-on: ubuntu-24.04"
    ))
    assert mod.check(tmp_path)["disabled_verified"] == 1
