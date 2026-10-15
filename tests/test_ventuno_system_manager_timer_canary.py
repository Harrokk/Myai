"""Offline-only system manager timer proof and privilege gate tests."""
import json
from pathlib import Path
from types import SimpleNamespace
import os
import pytest
from scripts import ventuno_system_manager_timer_canary as gate
from scripts import ventuno_htp_local_recovery_canary as marker


def temp_sandbox(tmp_path):
    p = tmp_path / "myai-htp-canary-abcdefabcdef"
    p.mkdir(mode=0o700)
    p.chmod(0o700)
    return p


def test_timer_is_managed_by_system_but_transient_worker_drops_to_arduino(tmp_path):
    p = temp_sandbox(tmp_path)
    args = gate.system_timer_argv(
        "myai-htp-canary-012345abcdef", p, Path(marker.__file__)
    )
    assert args[:5] == [
        "/usr/bin/sudo", "-n", "/usr/bin/systemd-run", "--system", "--quiet"
    ]
    assert "--unit=myai-htp-canary-012345abcdef" in args
    assert "--on-active=5s" in args
    assert "--property=User=arduino" in args
    assert "--property=Group=arduino" in args
    assert "--property=NoNewPrivileges=yes" in args
    assert "--timer-property=AccuracySec=1s" in args
    assert args[-2] == "--fire"
    assert args[-1] == str(p)
    assert "--collect" in args
    assert "myai-geniex.service" not in " ".join(args)
    assert "actions.runner." not in " ".join(args)
    assert "systemctl" not in args
    assert "--shell" not in args


def test_check_is_noninteractive_sudo_listing_only():
    commands = []
    def fake(args, **kwargs):
        commands.append(args)
        assert kwargs["timeout"] == 6
        assert kwargs["check"] is False
        return SimpleNamespace(returncode=0, stdout=b"SECRET", stderr=b"SECRET")
    assert gate.permission_check(run=fake) is True
    assert commands == [[
        "/usr/bin/sudo", "-n", "-l", "/usr/bin/systemd-run"
    ]]


def test_password_required_cannot_become_root_mutation(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: False,
        call=lambda *a, **k: pytest.fail("no system-manager call"),
    )
    assert result["status"] == "no_go_noninteractive_systemd_run_privilege_unavailable"
    assert result["transient_system_timer_submitted"] is False
    assert result["geniex_or_myai_services_changed"] is False
    assert not list(tmp_path.iterdir())


def test_no_optin_does_not_even_query_sudo(tmp_path, monkeypatch):
    monkeypatch.delenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", raising=False)
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: pytest.fail("no permission query authorized"),
    )
    assert result["status"] == "no_go_explicit_one_shot_opt_in_missing"


@pytest.mark.parametrize("arch,user", [
    ("x86_64", "arduino"), ("aarch64", "root"),
    ("aarch64", "other"), ("aarch64", None),
])
def test_identity_guard_rejects_unknown_runners(tmp_path, monkeypatch, arch, user):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    # user None may fall back to env USER, deliberately force untrusted.
    if user is None:
        monkeypatch.setenv("USER", "unknown")
    result = gate.run_canary(
        runner_temp=tmp_path, arch=arch, user=user,
        check=lambda: pytest.fail("no permission query"),
    )
    assert result["status"] == "no_go_untrusted_runner_identity"


def test_success_is_real_controller_exit_marker_only_not_runner_disconnect(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    calls = []
    def fake_command(argv, *, timeout):
        argv = list(argv)
        calls.append(argv)
        if argv[0] == gate.SUDO:
            assert "--system" in argv
            assert "--property=User=arduino" in argv
            return SimpleNamespace(returncode=0)
        assert argv[-2] == "--controller"
        assert marker.controller_crash(argv[-1]) == 73
        assert marker.timer_fire(argv[-1]) == 0
        return SimpleNamespace(returncode=73)
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: True, call=fake_command,
        sleeper=lambda seconds: pytest.fail("already triggered marker"),
    )
    assert result["status"] == "system_manager_timer_survived_controller_exit"
    assert result["system_manager_permission_available"] is True
    assert result["transient_system_timer_submitted"] is True
    assert result["disposable_controller_exit_observed"] is True
    assert result["independent_system_timer_restored_fake_marker"] is True
    assert result["transient_service_drops_to_arduino"] is True
    assert result["runner_disconnect_recovery_verified"] is False
    assert result["reboot_recovery_verified"] is False
    assert result["geniex_or_myai_services_changed"] is False
    assert result["persistent_system_timer_installed"] is False
    assert len(calls) == 2
    assert list(tmp_path.iterdir()) == []


def test_manager_rejected_exits_before_controller(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    calls = []
    def run(args, **kw):
        calls.append(args)
        return SimpleNamespace(returncode=1, stderr=b"secret")
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: True, call=run,
    )
    assert result["status"] == "no_go_system_manager_timer_launch_denied"
    assert result["disposable_controller_exit_observed"] is False
    assert len(calls) == 1
    assert "secret" not in json.dumps(result)
    assert list(tmp_path.iterdir()) == []


def test_disposable_controller_failure_never_claims_rollback(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    def call(args, **kwargs):
        if args[0] == gate.SUDO:
            return SimpleNamespace(returncode=0)
        return SimpleNamespace(returncode=73)
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: True, call=call,
    )
    assert result["status"] == "no_go_disposable_controller_not_verified"
    assert result["independent_system_timer_restored_fake_marker"] is False


def test_timeout_result_not_misrepresented_as_success(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    def call(args, **kwargs):
        if args[0] == gate.SUDO:
            return SimpleNamespace(returncode=0)
        marker.controller_crash(args[-1])
        return SimpleNamespace(returncode=73)
    def fake_clock():
        fake_clock.count += 1
        return float(fake_clock.count)
    fake_clock.count = 0
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: True, call=call,
        sleeper=lambda *_: None, now=fake_clock, max_wait=0,
    )
    assert result["status"] == "no_go_system_timer_did_not_restore_within_limit"
    assert result["independent_system_timer_restored_fake_marker"] is False


def test_bad_sandbox_or_target_unit_does_not_obtain_sudo_permission(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    alias = tmp_path / "alias"
    alias.symlink_to(tmp_path)
    r = gate.run_canary(
        runner_temp=alias, arch="aarch64", user="arduino",
        check=lambda: pytest.fail("untrusted temp dir"),
    )
    assert r["status"] == "no_go_runner_temp_unavailable"
    p = temp_sandbox(tmp_path)
    with pytest.raises(ValueError):
        gate.system_timer_argv("myai-geniex.service", p, marker.__file__)


def test_probe_exposes_no_sensitive_service_or_sudo_output(tmp_path, monkeypatch):
    monkeypatch.setenv("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY", "yes")
    result = gate.run_canary(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        check=lambda: False,
    )
    encoded = json.dumps(result)
    assert "/home/" not in encoded and "sudoers" not in encoded
    assert result["private_paths_logs_or_credentials_exported"] is False
    assert result["runner_service_stopped_or_changed"] is False
    assert result["htp_qnn_or_inference_executed"] is False
