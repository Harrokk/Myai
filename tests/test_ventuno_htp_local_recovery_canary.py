"""Pure simulated canary tests. No real systemd-run or service mutation."""
import json
from pathlib import Path
from types import SimpleNamespace
import os

import pytest

from scripts import ventuno_htp_local_recovery_canary as canary


def sandbox(tmp_path):
    path = tmp_path / "myai-htp-canary-test"
    path.mkdir(mode=0o700)
    path.chmod(0o700)
    return path


def test_controller_and_timer_only_touch_fixed_fake_markers(tmp_path):
    root = sandbox(tmp_path)
    assert canary.controller_crash(root) == 73
    assert canary.timer_fire(root) == 0
    assert canary._marker_is(root, canary.PAUSED, b"paused")
    assert canary._marker_is(root, canary.RESTORED, b"restored")
    assert sorted(x.name for x in root.iterdir()) == [
        canary.PAUSED, canary.RESTORED,
    ]
    assert canary.timer_fire(root) == 1  # O_EXCL forbids overwrite


def test_timer_will_not_restore_without_fake_paused_state(tmp_path):
    root = sandbox(tmp_path)
    assert canary.timer_fire(root) == 1
    assert not (root / canary.RESTORED).exists()


def test_invalid_directory_does_not_touch_any_other_file(tmp_path):
    good = sandbox(tmp_path)
    secret = tmp_path / "sensitive-target"
    secret.write_text("untouched")
    alias = tmp_path / "myai-htp-canary-link"
    alias.symlink_to(good, target_is_directory=True)
    assert not canary._private_sandbox(alias)
    assert canary.controller_crash(alias) == 1
    assert canary.timer_fire(alias) == 1
    assert canary._create_once(good, "sensitive-target", b"bad") is False
    assert secret.read_text() == "untouched"


def test_timer_command_no_sudo_system_manager_or_real_service_names(tmp_path):
    root = sandbox(tmp_path)
    cmd = canary.timer_command(
        "myai-htp-canary-012345abcdef", root, Path(canary.__file__)
    )
    assert cmd[:3] == ["systemd-run", "--user", "--quiet"]
    assert "--on-active=4s" in cmd
    assert "--timer-property=AccuracySec=1s" in cmd
    assert "--property=NoNewPrivileges=yes" in cmd
    assert "--property=UMask=0077" in cmd
    assert "--fire" in cmd and cmd[-1] == str(root)
    assert not any(x in cmd for x in ["--system", "sudo", "systemctl",
                                      "myai-geniex.service",
                                      "myai-ventuno.service"])


@pytest.mark.parametrize("bad", [
    "myai-geniex", "myai-htp-canary-attacker", "myai-htp-canary-012345678g",
    "myai-htp-canary-01234", "myai-htp-canary-012345abcde;rm",
])
def test_untrusted_unit_name_rejected(tmp_path, bad):
    root = sandbox(tmp_path)
    with pytest.raises(ValueError):
        canary.timer_command(bad, root, canary.__file__)


def test_simulated_independent_timer_returned_after_controller_crash(tmp_path):
    events = []
    def fake_timer(args, timeout):
        events.append("timer_armed")
        assert args[0] == "systemd-run" and args[1] == "--user"
        return SimpleNamespace(returncode=0)
    def fake_controller(args, timeout):
        events.append("controller_died")
        assert args[-2] == "--controller"
        root = Path(args[-1])
        assert canary.controller_crash(root) == 73
        assert canary.timer_fire(root) == 0
        events.append("fake_local_timer_fired")
        return SimpleNamespace(returncode=73)
    result = canary.exercise(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        timer_runner=fake_timer, controller_runner=fake_controller,
        sleep=lambda *_: pytest.fail("should have recovered synchronously"),
    )
    assert result["status"] == "user_systemd_canary_survived_controller_exit_only"
    assert events == ["timer_armed", "controller_died", "fake_local_timer_fired"]
    assert result["independent_timer_restored_synthetic_marker"] is True
    assert result["controller_process_terminated_before_restore"] is True
    assert result["runner_disconnect_or_reboot_recovery_verified"] is False
    assert result["real_service_stop_start_restart_performed"] is False
    assert result["geniex_or_myai_modified"] is False
    assert result["persistent_system_rollback_installed"] is False
    assert not any(x.name.startswith(canary.PREFIX) for x in tmp_path.iterdir())
    assert "arduino" not in json.dumps(result)


def test_user_manager_unavailable_is_no_go_never_sudo_fallback(tmp_path):
    commands = []
    def denied(args, timeout):
        commands.append(args)
        return SimpleNamespace(returncode=1, stderr=b"private bus error")
    result = canary.exercise(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        timer_runner=denied,
        controller_runner=lambda *a, **kw: pytest.fail("no controller after failed timer"),
    )
    assert result["status"] == "no_go_user_systemd_timer_unavailable"
    assert result["unprivileged_user_timer_armed"] is False
    assert len(commands) == 1 and commands[0][1] == "--user"
    assert "private bus error" not in json.dumps(result)
    assert result["geniex_or_myai_modified"] is False


def test_controller_crash_unverified_fails_closed(tmp_path):
    result = canary.exercise(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        timer_runner=lambda *a, **k: SimpleNamespace(returncode=0),
        controller_runner=lambda *a, **k: SimpleNamespace(returncode=73),
    )
    assert result["status"] == "no_go_disposable_controller_crash_not_verified"
    assert result["independent_timer_restored_synthetic_marker"] is False


def test_no_time_budget_is_no_go_without_wait(tmp_path):
    def fake_controller(args, timeout):
        assert canary.controller_crash(args[-1]) == 73
        return SimpleNamespace(returncode=73)
    now = [0]
    def clock():
        now[0] += 1
        return now[0]
    result = canary.exercise(
        runner_temp=tmp_path, arch="aarch64", user="arduino",
        timer_runner=lambda *a, **k: SimpleNamespace(returncode=0),
        controller_runner=fake_controller, max_wait=0,
        clock=clock, sleep=lambda *_: None,
    )
    assert result["status"] == "no_go_user_timer_did_not_fire_within_budget"
    assert result["independent_timer_restored_synthetic_marker"] is False


@pytest.mark.parametrize("arch,user", [
    ("x86_64", "arduino"),
    ("aarch64", "root"),
    ("aarch64", "github"),
])
def test_other_execution_contexts_rejected_without_temp_actions(tmp_path, arch, user):
    result = canary.exercise(
        runner_temp=tmp_path, arch=arch, user=user,
        timer_runner=lambda *a, **kw: pytest.fail("board-only"),
    )
    assert result["status"] == "no_go_not_ventuno_runner"
    assert list(tmp_path.iterdir()) == []


def test_no_user_temp_and_symlink_are_rejected(tmp_path):
    target = tmp_path / "actual"
    target.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(target)
    for path in (alias, tmp_path / "nonexistent"):
        result = canary.exercise(
            runner_temp=path, arch="aarch64", user="arduino",
            timer_runner=lambda *a, **kw: pytest.fail("no user manager"),
        )
        assert result["status"] == "no_go_runner_temp_untrusted"
