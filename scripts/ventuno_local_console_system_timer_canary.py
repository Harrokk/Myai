"""Local-terminal-only synthetic system-manager timer proof for VENTUNO Q.

Operator must open an actual interactive terminal ON THE BOARD. Nothing
in GitHub Actions can enter sudo credentials. The only privileged
request is ONE explicitly authenticated systemd-run --system transient
timer. The timer fires a known fixed fake-marker callback under
User=arduino; no real GenieX/MyAI/runner service is touched.

NO sudoers edits, shell, embedded passwords, maintenance lease, QNN, HTP,
reboot or live service stop/start. A success proves the system-manager
timer survived a disposable controller exit only; NOT disconnected GitHub
runner, reboot, an actual rollback, or NPU execution.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import time

from scripts import ventuno_htp_local_recovery_canary as marker
from scripts.ventuno_system_manager_timer_canary import (
    FIXED_USER, MAX_WAIT_SECONDS, SYSTEMD_RUN,
    system_timer_argv,
)

# One interactive sudo challenge to the already documented systemd-run
# utility. Password entry stays entirely in the board's local TTY.
SUDO = "/usr/bin/sudo"
LOCAL_ARGS = ("--local-terminal-only", "--fake-markers")
MAX_LAUNCH_SECONDS = 20


def _current_user():
    """Require the effective uid, not an untrusted USER environment hint."""
    try:
        import pwd
        return pwd.getpwuid(os.geteuid()).pw_name
    except (KeyError, OSError):
        return None


def _eligible(*, arch, username, uid, interactive, github_actions,
              local_opt_in):
    return (
        arch == "aarch64"
        and username == FIXED_USER
        and type(uid) is int and uid > 0
        and interactive is True
        and github_actions is False
        and local_opt_in is True
    )


def _sudo_argv(unit, scratch, callback):
    """Only the pre-reviewed fake marker command; no user-supplied args."""
    original = system_timer_argv(unit, scratch, callback)
    if original[:3] != [SUDO, "-n", SYSTEMD_RUN]:
        raise ValueError("unreviewed timer command")
    if (original[-2:] != ["--fire", str(scratch)]
            or "--property=User=arduino" not in original
            or "--property=Group=arduino" not in original
            or not original[3:]):
        raise ValueError("unreviewed timer callback")
    # '-k' forces a fresh local TTY authorization instead of assuming
    # cached sudo credentials. It does not modify sudoers.
    return [SUDO, "-k", "--", *original[2:]]


def _interactive_timer_call(argv, *, timeout):
    # Do NOT capture sudo stderr: a password prompt needs a local TTY.
    # stdout is discarded; no raw systemd output in the JSON summary.
    return subprocess.run(
        argv,
        stdin=None, stdout=subprocess.DEVNULL, stderr=None,
        check=False, timeout=timeout,
    )


def _disposable_controller(argv, *, timeout):
    # Entirely unprivileged subprocess; only a private mock marker.
    return subprocess.run(
        argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL, check=False, timeout=timeout,
    )


def exercise_local(*, root=None, arch=None, username=None, uid=None,
                   interactive=None, github_actions=None, opt_in=False,
                   timer_call=_interactive_timer_call,
                   controller_call=_disposable_controller,
                   clock=time.monotonic, sleep=time.sleep,
                   max_wait=MAX_WAIT_SECONDS):
    result = {
        "probe": "ventuno_local_console_system_timer_fake_rollback",
        "status": "no_go",
        "interactive_board_operator_present": False,
        "one_system_timer_armed": False,
        "controller_completed_and_exited": False,
        "independent_fake_restoration_observed": False,
        "local_password_or_sudo_output_collected": False,
        "real_services_changed": False,
        "github_runner_changed_or_stopped": False,
        "privileged_restore_handler_installed": False,
        "htp_npu_execution_or_profile_measured": False,
        "runner_disconnect_recovery_verified": False,
        "actual_reboot_recovery_verified": False,
        "private_paths_secrets_or_logs_exported": False,
    }
    arch = platform.machine().lower() if arch is None else arch
    username = _current_user() if username is None else username
    uid = os.geteuid() if uid is None else uid
    interactive = (sys.stdin.isatty() and sys.stderr.isatty()
                   if interactive is None else interactive)
    github_actions = (
        os.environ.get("GITHUB_ACTIONS", "").lower() == "true"
        if github_actions is None else github_actions
    )
    if not _eligible(
        arch=arch, username=username, uid=uid,
        interactive=interactive, github_actions=github_actions,
        local_opt_in=opt_in,
    ):
        result["status"] = "no_go_local_board_tty_and_explicit_opt_in_required"
        return result
    result["interactive_board_operator_present"] = True
    root = Path(tempfile.gettempdir() if root is None else root)
    if not root.is_absolute() or not root.is_dir() or root.is_symlink():
        result["status"] = "no_go_untrusted_temporary_directory"
        return result
    temp = None
    try:
        temp = Path(tempfile.mkdtemp(prefix=marker.PREFIX, dir=root))
        temp.chmod(0o700)
        callback = Path(marker.__file__).resolve()
        unit = marker.PREFIX + secrets.token_hex(6)
        argv = _sudo_argv(unit, temp, callback)
        try:
            launch = timer_call(argv, timeout=MAX_LAUNCH_SECONDS)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            launch = None
        if launch is None or launch.returncode != 0:
            result["status"] = "no_go_local_sudo_or_systemd_timer_failed"
            return result
        result["one_system_timer_armed"] = True

        try:
            controller = controller_call([
                sys.executable, "-I", str(callback),
                "--controller", str(temp),
            ], timeout=5)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            controller = None
        if (controller is None or controller.returncode != 73
                or not marker._marker_is(temp, marker.PAUSED, b"paused")):
            result["status"] = "no_go_disposable_controller_not_verified"
            return result
        result["controller_completed_and_exited"] = True

        end = clock() + min(max(float(max_wait), 0), MAX_WAIT_SECONDS)
        while clock() <= end:
            if marker._marker_is(temp, marker.RESTORED, b"restored"):
                result["independent_fake_restoration_observed"] = True
                result["status"] = "local_system_timer_restored_marker_after_controller_exit"
                return result
            sleep(0.25)
        result["status"] = "no_go_timer_not_observed_within_bounded_window"
        return result
    except (OSError, ValueError, TypeError):
        result["status"] = "no_go_local_sandbox_or_time_failure"
        return result
    finally:
        if temp is not None and marker._private_sandbox(temp):
            shutil.rmtree(temp)


if __name__ == "__main__":
    if tuple(sys.argv[1:]) != LOCAL_ARGS:
        sys.exit(2)
    try:
        report = exercise_local(opt_in=True)
    except Exception:
        report = {
            "probe": "ventuno_local_console_system_timer_fake_rollback",
            "status": "no_go_local_unexpected_failure",
            "real_services_changed": False,
            "privileged_restore_handler_installed": False,
            "htp_npu_execution_or_profile_measured": False,
            "runner_disconnect_recovery_verified": False,
        }
    print("MYAI_LOCAL_SYSTEM_TIMER_CANARY_JSON=" + json.dumps(
        report, sort_keys=True
    ))
    sys.exit(0 if report["independent_fake_restoration_observed"] else 1)
