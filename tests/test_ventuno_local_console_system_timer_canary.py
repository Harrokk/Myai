"""Local-terminal fake systemd timer: all effects fully mocked, never sudo."""
import json
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from scripts import ventuno_local_console_system_timer_canary as subject
from scripts import ventuno_htp_local_recovery_canary as marker


def execute(tmp_path, *, timer=None, controller=None, interactive=True,
            github_actions=False, uid=1000, username="arduino", arch="aarch64",
            wait=0):
    return subject.exercise_local(
        root=tmp_path, arch=arch, username=username, uid=uid,
        interactive=interactive, github_actions=github_actions,
        opt_in=True, timer_call=timer or (
            lambda args, **kw: SimpleNamespace(returncode=0)
        ),
        controller_call=controller or (
            lambda args, **kw: SimpleNamespace(returncode=73)
        ),
        max_wait=wait, clock=lambda: 100.0,
        sleep=lambda s: None,
    )


@pytest.mark.parametrize("alter", [
    {"arch": "x86_64"},
    {"username": "root"},
    {"username": "github"},
    {"uid": 0},
    {"uid": True},
    {"interactive": False},
    {"github_actions": True},
])
def test_guard_rejects_nonlocal_or_ci_context_without_touching_files(tmp_path, alter):
    r = execute(
        tmp_path, timer=lambda *a, **kw: pytest.fail("no sudo"),
        **alter,
    )
    assert r["status"] == "no_go_local_board_tty_and_explicit_opt_in_required"
    assert r["one_system_timer_armed"] is False
    assert not list(tmp_path.iterdir())


def test_requires_explicit_single_local_command_optin(tmp_path):
    r = subject.exercise_local(
        root=tmp_path, arch="aarch64", username="arduino", uid=1000,
        interactive=True, github_actions=False, opt_in=False,
        timer_call=lambda *a, **kw: pytest.fail("no local consent"),
    )
    assert r["status"] == "no_go_local_board_tty_and_explicit_opt_in_required"


def test_approved_argv_runs_as_arduino_and_asks_locally_for_sudo_password(tmp_path):
    p = tmp_path / "myai-htp-canary-0123456789ab"
    p.mkdir(mode=0o700)
    argv = subject._sudo_argv(
        "myai-htp-canary-123456abcdef", p, marker.__file__,
    )
    assert argv[:4] == [
        "/usr/bin/sudo", "-k", "--", "/usr/bin/systemd-run"
    ]
    assert "--system" in argv and "--quiet" in argv
    assert "--on-active=5s" in argv
    assert "--property=User=arduino" in argv
    assert "--property=Group=arduino" in argv
    assert "--property=NoNewPrivileges=yes" in argv
    assert "--property=UMask=0077" in argv
    assert "--collect" in argv
    assert argv[-2:] == ["--fire", str(p)]
    assert "myai-geniex.service" not in argv
    assert "myai-ventuno.service" not in argv
    assert "actions.runner." not in " ".join(argv)
    assert "systemctl" not in argv
    assert "--user" not in argv
    assert "sudoers" not in argv


def test_sudo_invocation_keeps_local_tty_stderr_and_stdin_open(monkeypatch):
    captured = []
    def fake_run(argv, **kwargs):
        captured.append((argv, kwargs))
        return SimpleNamespace(returncode=0)
    monkeypatch.setattr(subject.subprocess, "run", fake_run)
    subject._interactive_timer_call(["/usr/bin/sudo", "-k"], timeout=20)
    assert captured[0][1]["stderr"] is None
    assert captured[0][1]["stdin"] is None
    assert captured[0][1]["stdout"] == subprocess.DEVNULL
    assert captured[0][1]["timeout"] == 20
    assert captured[0][1]["check"] is False


def test_independent_restore_only_after_controller_has_exited(tmp_path):
    timeline = []
    sandbox = {}
    def timer(argv, **kwargs):
        assert argv[:3] == ["/usr/bin/sudo", "-k", "--"]
        assert kwargs["timeout"] == subject.MAX_LAUNCH_SECONDS
        timeline.append("timer_submitted")
        sandbox["path"] = Path(argv[-1])
        return SimpleNamespace(returncode=0)
    def controller(argv, **kwargs):
        assert argv[-2:] == ["--controller", str(sandbox["path"])]
        timeline.append("controller_started")
        assert marker.controller_crash(sandbox["path"]) == 73
        timeline.append("controller_exited")
        return SimpleNamespace(returncode=73)
    def sleep(duration):
        assert timeline[-1] == "controller_exited"
        assert marker.timer_fire(sandbox["path"]) == 0
        timeline.append("system_manager_mock_fired")
    fake_now = [0]
    def now():
        fake_now[0] += 0.4
        return fake_now[0]
    r = subject.exercise_local(
        root=tmp_path, arch="aarch64", username="arduino", uid=1000,
        interactive=True, github_actions=False, opt_in=True,
        timer_call=timer, controller_call=controller,
        clock=now, sleep=sleep, max_wait=2,
    )
    assert r["status"] == "local_system_timer_restored_marker_after_controller_exit"
    assert r["one_system_timer_armed"] is True
    assert r["controller_completed_and_exited"] is True
    assert r["independent_fake_restoration_observed"] is True
    assert timeline == [
        "timer_submitted", "controller_started", "controller_exited",
        "system_manager_mock_fired",
    ]
    assert not list(tmp_path.iterdir())
    assert r["runner_disconnect_recovery_verified"] is False
    assert r["actual_reboot_recovery_verified"] is False
    assert r["real_services_changed"] is False
    assert r["htp_npu_execution_or_profile_measured"] is False


def test_sudo_failed_without_password_never_launches_fake_controller(tmp_path):
    r = execute(
        tmp_path,
        timer=lambda argv, **kw: SimpleNamespace(returncode=1),
        controller=lambda *a, **kw: pytest.fail("no controller before sudo"),
    )
    assert r["status"] == "no_go_local_sudo_or_systemd_timer_failed"
    assert r["one_system_timer_armed"] is False
    assert r["controller_completed_and_exited"] is False
    assert not list(tmp_path.iterdir())


def test_controller_exits_73_without_marker_is_not_false_success(tmp_path):
    r = execute(tmp_path)
    assert r["status"] == "no_go_disposable_controller_not_verified"
    assert r["independent_fake_restoration_observed"] is False


def test_marker_absent_after_controller_is_timeout_not_recovery(tmp_path):
    def ctrl(argv, **kwargs):
        assert marker.controller_crash(argv[-1]) == 73
        return SimpleNamespace(returncode=73)
    counter = [0]
    def clock():
        counter[0] += 1
        return counter[0]
    r = subject.exercise_local(
        root=tmp_path, arch="aarch64", username="arduino", uid=1000,
        interactive=True, github_actions=False, opt_in=True,
        timer_call=lambda *a, **kw: SimpleNamespace(returncode=0),
        controller_call=ctrl, clock=clock, sleep=lambda *a: None,
        max_wait=0,
    )
    assert r["status"] == "no_go_timer_not_observed_within_bounded_window"
    assert r["independent_fake_restoration_observed"] is False


def test_symlink_root_does_not_prompt_for_sudo(tmp_path):
    root = tmp_path / "root"
    root.mkdir()
    alias = tmp_path / "link"
    alias.symlink_to(root, target_is_directory=True)
    r = subject.exercise_local(
        root=alias, arch="aarch64", username="arduino", uid=1000,
        interactive=True, github_actions=False, opt_in=True,
        timer_call=lambda *a, **kw: pytest.fail("no sudo for symlink"),
    )
    assert r["status"] == "no_go_untrusted_temporary_directory"


def test_logs_never_leak_paths_sudo_password_or_real_model_data(tmp_path):
    r = execute(
        tmp_path,
        timer=lambda argv, **kw: SimpleNamespace(
            returncode=1, stderr=b"private: sudo password at /home/arduino/.ssh"
        ),
    )
    serialized = json.dumps(r)
    assert "private: sudo password" not in serialized.lower()
    assert "/home/" not in serialized
    assert r["local_password_or_sudo_output_collected"] is False
    assert r["private_paths_secrets_or_logs_exported"] is False


def test_no_automatic_sudoers_change_or_systemd_unit_install(tmp_path):
    r = execute(
        tmp_path,
        timer=lambda *a, **kw: SimpleNamespace(returncode=1),
    )
    for key in (
        "privileged_restore_handler_installed", "real_services_changed",
        "github_runner_changed_or_stopped",
        "htp_npu_execution_or_profile_measured",
    ):
        assert r[key] is False
