"""Safe system-manager timer canary, independent of a disposable controller.

This is an isolated temporary test, NEVER a real system recovery:
- only run as arduino on the trusted Ventuno ARM64 runner, with explicit
  opt-in and a private scratch dir under RUNNER_TEMP
- first check noninteractive sudo permission for the exact systemd-run
  executable; never request passwords, enable sudoers or use polkit
- if allowed, systemd-run registers a transient *system-manager* timer
  whose one-shot service DROPS privileges back to User=arduino
- the timer may only call an existing, vetted fake-marker script with
  --fire; it never opens DSP or stops/starts GenieX, MyAI or runner
- separate controller exits with code 73 after writing a fake marker
- prove that the timer can write a fake restoration marker after that
  independent controller is no longer running

A passing canary does NOT prove resilience to board reboot, systemd PID1
failure, real service recovery or GitHub runner disconnection. It does
not install/enable production units or modify sudoers.
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

SUDO = "/usr/bin/sudo"
SYSTEMD_RUN = "/usr/bin/systemd-run"
FIXED_USER = "arduino"
MAX_WAIT_SECONDS = 28.0


def permission_check(run=subprocess.run):
    """No command execution authorization: sudo -n -l is listing only."""
    try:
        cp = run(
            [SUDO, "-n", "-l", SYSTEMD_RUN],
            capture_output=True, check=False, timeout=6,
        )
        return cp.returncode == 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def system_timer_argv(unit, scratch, source):
    # Only a vetted fake-marker callback under the current SHA checkout
    # is permitted. Crucially the service itself runs as arduino, not root.
    base = marker.timer_command(unit, scratch, source)
    assert base[0] == "systemd-run" and base[1] == "--user"
    return [
        SUDO, "-n", SYSTEMD_RUN, "--system", "--quiet",
        "--unit=" + unit, "--on-active=5s",
        "--timer-property=AccuracySec=1s",
        "--property=User=arduino", "--property=Group=arduino",
        "--property=NoNewPrivileges=yes",
        "--property=UMask=0077",
        "--collect", "/usr/bin/python3", "-I",
        str(Path(source).resolve()), "--fire", str(Path(scratch)),
    ]


def command(argv, *, timeout):
    return subprocess.run(
        argv, capture_output=True, check=False, timeout=timeout,
    )


def run_canary(*, runner_temp, arch=None, user=None,
               check=permission_check, call=command,
               sleeper=time.sleep, now=time.monotonic,
               max_wait=MAX_WAIT_SECONDS):
    report = {
        "probe": "ventuno_system_manager_timer_synthetic_recovery_once",
        "status": "no_go",
        "system_manager_permission_available": False,
        "transient_system_timer_submitted": False,
        "transient_service_drops_to_arduino": True,
        "disposable_controller_exit_observed": False,
        "independent_system_timer_restored_fake_marker": False,
        "runner_service_stopped_or_changed": False,
        "geniex_or_myai_services_changed": False,
        "systemd_manager_reconfigured": False,
        "persistent_system_timer_installed": False,
        "sudoers_modified": False,
        "htp_qnn_or_inference_executed": False,
        "runner_disconnect_recovery_verified": False,
        "reboot_recovery_verified": False,
        "private_paths_logs_or_credentials_exported": False,
    }
    arch = arch if arch is not None else platform.machine().lower()
    user = user if user is not None else os.environ.get("USER")
    if arch != "aarch64" or user != FIXED_USER or os.geteuid() == 0:
        report["status"] = "no_go_untrusted_runner_identity"
        return report
    if os.environ.get("MYAI_ALLOW_SYSTEM_MANAGER_FAKE_CANARY") != "yes":
        report["status"] = "no_go_explicit_one_shot_opt_in_missing"
        return report
    root = Path(runner_temp)
    if not root.is_dir() or root.is_symlink():
        report["status"] = "no_go_runner_temp_unavailable"
        return report
    if not check():
        report["status"] = "no_go_noninteractive_systemd_run_privilege_unavailable"
        return report
    report["system_manager_permission_available"] = True
    scratch = None
    try:
        scratch = Path(tempfile.mkdtemp(prefix=marker.PREFIX, dir=root))
        scratch.chmod(0o700)
        unit = marker.PREFIX + secrets.token_hex(6)
        # The callback is the existing fake-marker script, never a
        # user-defined systemctl command or generated executable.
        source = Path(marker.__file__).resolve()
        argv = system_timer_argv(unit, scratch, source)
        try:
            launched = call(argv, timeout=8)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            launched = None
        if launched is None or launched.returncode != 0:
            report["status"] = "no_go_system_manager_timer_launch_denied"
            return report
        report["transient_system_timer_submitted"] = True

        # The ephemeral timer belongs to PID1. Controller writes its
        # marker in its own process and exits before we poll for restore.
        try:
            controller = call(
                [sys.executable, "-I", str(source),
                 "--controller", str(scratch)],
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            controller = None
        if (controller is None or controller.returncode != 73
                or not marker._marker_is(scratch, marker.PAUSED, b"paused")):
            report["status"] = "no_go_disposable_controller_not_verified"
            return report
        report["disposable_controller_exit_observed"] = True

        end = now() + min(max(float(max_wait), 0), MAX_WAIT_SECONDS)
        while now() <= end:
            if marker._marker_is(scratch, marker.RESTORED, b"restored"):
                report["independent_system_timer_restored_fake_marker"] = True
                report["status"] = "system_manager_timer_survived_controller_exit"
                return report
            sleeper(0.25)
        report["status"] = "no_go_system_timer_did_not_restore_within_limit"
        return report
    except (OSError, ValueError, TypeError):
        report["status"] = "no_go_sandbox_setup_or_check_failed"
        return report
    finally:
        if scratch is not None and marker._private_sandbox(scratch):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    try:
        result = run_canary(runner_temp=os.environ.get("RUNNER_TEMP", ""))
    except Exception:
        result = {
            "probe": "ventuno_system_manager_timer_synthetic_recovery_once",
            "status": "no_go_unexpected_exception",
            "geniex_or_myai_services_changed": False,
            "runner_service_stopped_or_changed": False,
            "htp_qnn_or_inference_executed": False,
            "private_paths_logs_or_credentials_exported": False,
        }
    print("MYAI_SYSTEM_TIMER_FAKE_CANARY_JSON=" + json.dumps(result, sort_keys=True))
