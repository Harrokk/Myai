"""Pure source-only tests for real Bubblewrap observer, no sandbox launched."""
import json
import os
import subprocess
from types import SimpleNamespace

import pytest

from core import selfdev_bwrap_observation as b


@pytest.fixture
def fixture(tmp_path):
    root = tmp_path / "fixture"
    root.mkdir(mode=0o700)
    root.chmod(0o700)
    path = root / "fixture.py"
    path.write_bytes(b.FIXTURE)
    path.chmod(0o600)
    return root


def observed(*, inode=321, digest=None, denied=True, returncode=0, stderr=""):
    return SimpleNamespace(
        returncode=returncode, stderr=stderr,
        stdout=json.dumps({
            "fixture_sha256": digest or b.FIXTURE_SHA256,
            "net_namespace_inode": inode,
            "file_mutation_denied": denied,
        }, sort_keys=True),
    )


def test_command_exclusively_uses_bubblewrap_readonly_source_and_unshared_all(fixture):
    command = b.build_command(
        bwrap="/usr/bin/bwrap", trusted_fixture_root=fixture
    )
    assert command[0] == "/usr/bin/bwrap"
    assert "--unshare-all" in command
    assert "--clearenv" in command
    assert "--new-session" in command
    assert "--die-with-parent" in command
    assert "--proc" in command
    assert "--dev" in command
    assert "--tmpfs" in command
    assert "--bind" not in command
    assert command[command.index("/workspace") - 2] == "--ro-bind"
    assert command[command.index("/workspace") - 1] == str(fixture)
    assert command[-5:] == ["/usr/bin/python3", "-I", "-B", "-c", b._TEST_SCRIPT]
    assert "file_mutation_denied" in b._TEST_SCRIPT
    assert "/proc/self/ns/net" in b._TEST_SCRIPT
    assert "/workspace/fixture.py" in b._TEST_SCRIPT


def test_real_observation_only_accepts_isolated_success(fixture):
    def runner(command, **kwargs):
        assert "--unshare-all" in command
        assert kwargs["max_output_bytes"] == 4096
        assert kwargs["timeout"] == b.LIMIT_SECONDS
        assert set(kwargs["env"]) == {
            "PATH", "HOME", "LC_ALL", "PYTHONDONTWRITEBYTECODE",
        }
        return observed(inode=500)
    result = b.observe(trusted_fixture_root=fixture, runner=runner, host_ns_inode=400)
    assert result.sandbox == "bubblewrap"
    assert result.network_isolated is True
    assert result.verifier_execution_observed_on_disposable_host is True
    assert result.fixture_sha256 == b.FIXTURE_SHA256
    assert result.independent_production_verifier_implemented is False
    assert result.production_deployment_authorized is False
    assert result.authorizes_mutation is False


@pytest.mark.parametrize("outcome", [
    observed(inode=400),  # same network namespace => fail
    observed(inode=500, digest="f" * 64),
    observed(inode=500, denied=False),
    observed(inode=500, returncode=1),
    observed(inode=500, stderr="unsafe"),
    SimpleNamespace(returncode=0, stderr="", stdout="{"),
    SimpleNamespace(returncode=0, stderr="", stdout="x" * 513),
    SimpleNamespace(returncode=True, stderr="", stdout="{}"),
    SimpleNamespace(returncode=0, stderr="", stdout=json.dumps({
        "fixture_sha256": b.FIXTURE_SHA256, "net_namespace_inode": 500,
        "file_mutation_denied": True, "production_approved": True
    })),
])
def test_fake_or_unsafe_sandbox_observation_rejected(fixture, outcome):
    with pytest.raises(RuntimeError):
        b.observe(trusted_fixture_root=fixture, host_ns_inode=400,
                  runner=lambda *a, **kw: outcome)


def test_missing_bwrap_is_never_replaced_with_unsandboxed_fallback(fixture):
    for name in ("", "/bin/sh", "bwrap", "/tmp/bwrap", "/usr/bin/python3"):
        with pytest.raises(ValueError):
            b.build_command(bwrap=name, trusted_fixture_root=fixture)


def test_missing_symlink_changed_or_writable_fixture_refused(fixture, tmp_path):
    path = fixture / "fixture.py"
    path.write_bytes(b"SAFE = 2\n")
    with pytest.raises(ValueError):
        b.build_command(bwrap="/usr/bin/bwrap", trusted_fixture_root=fixture)
    path.unlink()
    path.symlink_to(tmp_path / "outside.py")
    with pytest.raises(PermissionError):
        b.build_command(bwrap="/usr/bin/bwrap", trusted_fixture_root=fixture)
    path.unlink()
    path.write_bytes(b.FIXTURE)
    path.chmod(0o666)
    with pytest.raises(PermissionError):
        b.build_command(bwrap="/usr/bin/bwrap", trusted_fixture_root=fixture)


def test_fixture_directory_cannot_be_group_writable(fixture):
    fixture.chmod(0o770)
    with pytest.raises(PermissionError):
        b.build_command(bwrap="/usr/bin/bwrap", trusted_fixture_root=fixture)


def test_host_runner_script_is_explicit_optin_and_never_authorizes_release():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    src = (root / "scripts/test_hosted_real_bwrap_observer.py").read_text()
    assert "MYAI_HOSTED_BWRAP_TEST" in src
    assert "MYAI_RUNNER_ENVIRONMENT" in src
    assert 'Ed25519PrivateKey.generate()' in src
    assert "observe(trusted_fixture_root=sandbox)" in src
    assert "issue_inspection_challenge(" in src
    assert "consume_signed_inspection(" in src
    assert '"trusted_independent_production_verifier": False' in src
    assert '"selfdev_promotion_authorized": False' in src
    assert '"production_deployment_authorized": False' in src
    assert "SelfDevPromotionManager" not in src


def test_hosted_workflow_fails_closed_without_relaxing_namespaces():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1]
    wf = (root / ".github/workflows/disposable-real-bwrap-observer.yml").read_text()
    assert "runs-on: ubuntu-22.04" in wf
    assert 'test "$RUNNER_ENVIRONMENT" = "github-hosted"' in wf
    assert "permissions:\n  contents: read" in wf
    assert "bubblewrap" in wf
    assert 'test "$(git -C "$MYAI_BWRAP_CHECKOUT" rev-parse HEAD)" = "$GITHUB_SHA"' in wf
    assert "MYAI_HOSTED_BWRAP_TEST=yes" in wf
    assert "kernel.apparmor_restrict_unprivileged_userns=0" not in wf
    assert "sysctl -w" not in wf
    assert "--share-net" not in wf
    assert "workflow_dispatch:" not in wf
    assert "/home/arduino/" not in wf
    assert "runs-on: [self-hosted" not in wf
    assert "sudo systemctl" not in wf
    assert "secrets." not in wf
