"""Independent source-only safety regression for old consent jobs."""
from scripts import ventuno_historical_consent_audit as check


def _fixture(tmp_path, *, active=False):
    directory = tmp_path / ".github/workflows"
    directory.mkdir(parents=True, exist_ok=True)
    for filename, job in check.BOARD_JOBS.items():
        mocked = (filename == "ventuno-geniex-lazy-htp-once.yml")
        lines = ["name: old one-time test", "on:", "  workflow_dispatch:",
                 "jobs:"]
        if mocked:
            lines += ["  mocked-safety:", "    runs-on: ubuntu-24.04",
                      "    steps:", "      - run: echo mock"]
        lines += [
            f"  {job}:",
            "    # Historical authorizations are stale",
            "    if: true" if active else "    if: false",
            "    runs-on: [self-hosted, Linux, ARM64, ventuno-q]",
            "    steps:", "      - run: echo fake",
        ]
        (directory / filename).write_text("\n".join(lines) + "\n")
    return directory


def test_twelve_real_historical_jobs_are_inert_on_audit_branch():
    report = check.audit()
    assert report["status"] == "historical-physical-jobs-quarantined"
    assert report["confirmed_job_disabled"] == 12
    assert report["actual_audio_or_model_executed"] is False
    assert report["old_consent_reused"] is False
    assert report["release_authorized"] is False


def test_fixtures_require_job_level_false(tmp_path):
    _fixture(tmp_path)
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 12
    _fixture(tmp_path, active=True)
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 0


def test_missing_symlink_and_duplicate_board_job_fail_closed(tmp_path):
    directory = _fixture(tmp_path)
    path = directory / "ventuno-microphone-consent-once.yml"
    path.unlink()
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 11
    path.symlink_to(tmp_path / "external.yml")
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 11
    path.unlink()
    _fixture(tmp_path)
    path.write_text(path.read_text() + "\n  microphone:\n    if: false\n")
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 11


def test_extra_self_hosted_job_cannot_escape_denial(tmp_path):
    directory = _fixture(tmp_path)
    file = directory / "ventuno-geniex-lazy-htp-once.yml"
    file.write_text(file.read_text() +
                    "  second-inference:\n    runs-on: [self-hosted]\n")
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 11


def test_step_false_does_not_disable_real_job(tmp_path):
    directory = _fixture(tmp_path, active=True)
    file = directory / "ventuno-usb-speaker-consent-once.yml"
    file.write_text(file.read_text() + "      - if: false\n        run: echo fake\n")
    assert check.audit(tmp_path)["confirmed_job_disabled"] == 0
