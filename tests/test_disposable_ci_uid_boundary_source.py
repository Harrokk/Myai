"""Source-only safety checks for a hosted, disposable, real-UID test.

No fork, chown, setuid, docker, production filesystem, or device operations
are executed in this pytest module. Integration executes only in Docker job.
"""
from pathlib import Path

import pytest

from scripts import test_disposable_ci_uid_boundary as boundary


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github/workflows/disposable-three-uid-ci-boundary.yml"
SCRIPT = ROOT / "scripts/test_disposable_ci_uid_boundary.py"


def test_ids_and_examples_are_disposable_only():
    assert len({boundary.CI_UID, boundary.RUNTIME_UID, boundary.UPDATER_UID}) == 3
    assert min(boundary.CI_UID, boundary.RUNTIME_UID, boundary.UPDATER_UID) >= 23000
    assert boundary.FAKE_GITHUB_TOKEN.startswith(b"fake-")
    assert boundary.FAKE_JOURNAL_KEY.startswith(b"fake-")


def test_permission_denial_helper_must_reject_unexpected_success():
    assert boundary.denied("test-only", lambda: (_ for _ in ()).throw(
        PermissionError("mock permission denied"))) == "test-only"
    with pytest.raises(AssertionError, match="Unexpected unprivileged access"):
        boundary.denied("test-only", lambda: None)


def test_no_host_account_change_on_import_or_unit_test():
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'if __name__ == "__main__":' in source
    assert "require_disposable_container()" in source
    assert 'MYAI_DISPOSABLE_UID_TEST' in source
    assert 'Path("/.dockerenv").exists()' in source
    assert "os.setgroups([])" in source
    assert "os.setgid(uid)" in source
    assert "os.setuid(uid)" in source
    assert "os.chown" in source  # Only invoked from the guarded Docker main path.


def test_hosted_job_has_strict_networkless_disposable_boundary():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "runs-on: ubuntu-24.04" in text
    assert "runs-on: [self-hosted" not in text
    assert "RUNNER_ENVIRONMENT: " + "${{ runner.environment }}" in text
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in text
    assert 'test "$(uname -m)" = "x86_64"' in text
    assert "permissions:\n  contents: read" in text
    assert "docker run --rm --network none --read-only" in text
    assert "--cap-drop ALL" in text
    assert "--cap-add SETUID --cap-add SETGID" in text
    assert "--security-opt no-new-privileges" in text
    assert "--tmpfs /tmp:rw,nosuid,nodev,size=32m" in text
    assert "--mount \"type=bind,src=$PWD/scripts/test_disposable_ci_uid_boundary.py," in text
    assert "dst=/opt/myai-three-uid-test.py,readonly\"" in text
    assert "sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258" in text
    assert '"$GITHUB_SHA"' in text
    assert "rev-parse HEAD" in text
    assert "on:\n  push:" in text
    assert "workflow_dispatch:" not in text
    assert "self-hosted" not in text
    assert "systemctl" not in text
    assert "/home/arduino/" not in text


def test_docker_workflow_cannot_mount_installed_project_or_secrets():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert text.count("type=bind") == 1
    assert "MYAI_DISPOSABLE_UID_TEST=yes" in text
    assert "GH_TOKEN" not in text
    assert "GITHUB_TOKEN" not in text
    assert "secrets." not in text
    assert "docker.sock" not in text
    assert "--privileged" not in text


def test_real_uid_test_reports_no_production_attestation():
    source = SCRIPT.read_text(encoding="utf-8")
    for expected in (
        '"production_touched": False',
        '"real_ventuno_acl_or_runner_policy_proven": False',
        '"real_verifier_signing_proven": False',
        '"physical_hardware_tests_authorized": False',
        '"production_deployment_authorized": False',
    ):
        assert expected in source
    assert "signing-key-read" in source
    assert "verification-forge" in source
    assert "memory-overwrite" in source
    assert "installed-code-write" in source
    assert "updater-staging-write" in source
    assert "rollback-backup-write" in source
    assert "runtime-ci-token-read" in source
