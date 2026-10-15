"""Sandbox-only systemd user-timer recovery canary for VENTUNO Q.

This is not a GenieX/MyAI maintenance executor. It may register ONE
short-lived *unprivileged user-manager* timer with a unique name. That
timer writes only a fixed 'restored' marker to a private 0700 temp
directory after a separate disposable 'controller' subprocess exits
with code 73. No actual system service is stopped/started/restarted.

The timer may survive a simulated controller crash while the GitHub
runner remains online. This does NOT establish survival of a failed
systemd manager, user-manager shutdown, board reboot, or GitHub runner
job termination. If the user systemd manager is inaccessible it is NO-GO:
do not fallback to system manager, sudo, nohup or background daemons.

A production rollback would require a persistent independently managed
root-owned timer and audited restoration handler, explicit permission,
actual systemd unit-state verification, an isolated HTP run procedure,
and proof of recovery after controller/runner disconnection and reboot.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time

PREFIX = "myai-htp-canary-"
UNIT_RE = re.compile(r"^myai-htp-canary-[0-9a-f]{12}$")
PAUSED = "synthetic-paused.txt"
RESTORED = "synthetic-restored.txt"
MAX_WAIT_SECONDS = 24.0


def _private_sandbox(path):
    """Validate one owned, non-symlink 0700 directory with known basename."""
    path = Path(path)
    if not path.is_absolute() or not path.name.startswith(PREFIX):
        return False
    try:
        data = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISDIR(data.st_mode)
        and stat.S_IMODE(data.st_mode) == 0o700
        and data.st_uid == os.geteuid()
        and not path.is_symlink()
    )


def _create_once(root, basename, contents):
    if not _private_sandbox(root) or basename not in {PAUSED, RESTORED}:
        return False
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(Path(root) / basename, flags, 0o600)
    except OSError:
        return False
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(contents)
            handle.flush()
            os.fsync(handle.fileno())
        return True
    except OSError:
        return False


def _marker_is(root, basename, expected):
    if not _private_sandbox(root) or basename not in {PAUSED, RESTORED}:
        return False
    path = Path(root) / basename
    try:
        if path.is_symlink() or not path.is_file():
            return False
        if path.stat().st_size != len(expected):
            return False
        return path.read_bytes() == expected
    except OSError:
        return False


def controller_crash(root):
    """Crash a disposable process after writing fake paused-state only."""
    if not _create_once(root, PAUSED, b"paused"):
        return 1
    # Intentional synthetic controller failure; never affects the runner.
    return 73


def timer_fire(root):
    """Only synthesize restoration of the private mock marker."""
    if not _marker_is(root, PAUSED, b"paused"):
        return 1
    return 0 if _create_once(root, RESTORED, b"restored") else 1


def timer_command(unit, sandbox, script):
    if not UNIT_RE.fullmatch(unit) or not _private_sandbox(sandbox):
        raise ValueError("bad-private-canary-identity")
    script = Path(script).resolve()
    if not script.is_file() or script.suffix != ".py":
        raise ValueError("missing-readonly-canary-script")
    return [
        "systemd-run", "--user", "--quiet",
        "--unit=" + unit,
        "--on-active=4s",
        "--timer-property=AccuracySec=1s",
        "--property=NoNewPrivileges=yes",
        "--property=UMask=0077",
        "--collect",
        "/usr/bin/python3", "-I", str(script),
        "--fire", str(sandbox),
    ]


def _run_command(args, *, timeout):
    return subprocess.run(
        args, capture_output=True, timeout=timeout, check=False,
    )


def exercise(*, runner_temp, arch=None, user=None, timer_runner=_run_command,
             controller_runner=_run_command, sleep=time.sleep,
             clock=time.monotonic, max_wait=MAX_WAIT_SECONDS):
    """Safe real-board canary, with injected runners for offline tests."""
    result = {
        "probe": "ventuno_local_user_systemd_recovery_canary",
        "status": "no_go",
        "real_board_arm64_arduino": False,
        "unprivileged_user_timer_armed": False,
        "disposable_controller_crash_observed": False,
        "independent_timer_restored_synthetic_marker": False,
        "controller_process_terminated_before_restore": False,
        "real_service_stop_start_restart_performed": False,
        "geniex_or_myai_modified": False,
        "npu_or_qnn_executed": False,
        "system_manager_or_sudo_used": False,
        "persistent_system_rollback_installed": False,
        "runner_disconnect_or_reboot_recovery_verified": False,
        "private_paths_or_logs_exported": False,
    }
    target_arch = arch if arch is not None else platform.machine().lower()
    target_user = user if user is not None else os.environ.get("USER")
    if target_arch != "aarch64" or target_user != "arduino":
        result["status"] = "no_go_not_ventuno_runner"
        return result
    result["real_board_arm64_arduino"] = True
    runner_temp = Path(runner_temp)
    if not runner_temp.is_dir() or runner_temp.is_symlink():
        result["status"] = "no_go_runner_temp_untrusted"
        return result
    scratch = None
    try:
        scratch = Path(tempfile.mkdtemp(prefix=PREFIX, dir=runner_temp))
        os.chmod(scratch, 0o700)
        unit = PREFIX + secrets.token_hex(6)
        command = timer_command(unit, scratch, Path(__file__))
        try:
            launched = timer_runner(command, timeout=8)
        except (OSError, subprocess.TimeoutExpired, ValueError):
            launched = None
        if launched is None or launched.returncode != 0:
            result["status"] = "no_go_user_systemd_timer_unavailable"
            return result
        result["unprivileged_user_timer_armed"] = True

        try:
            controller = controller_runner(
                [sys.executable, "-I", str(Path(__file__).resolve()),
                 "--controller", str(scratch)],
                timeout=5,
            )
        except (OSError, subprocess.TimeoutExpired, ValueError):
            controller = None
        if controller is None or controller.returncode != 73 or not _marker_is(
            scratch, PAUSED, b"paused"
        ):
            result["status"] = "no_go_disposable_controller_crash_not_verified"
            return result
        result["disposable_controller_crash_observed"] = True

        deadline = clock() + max(0, min(float(max_wait), MAX_WAIT_SECONDS))
        while clock() <= deadline:
            if _marker_is(scratch, RESTORED, b"restored"):
                result["independent_timer_restored_synthetic_marker"] = True
                result["controller_process_terminated_before_restore"] = True
                result["status"] = "user_systemd_canary_survived_controller_exit_only"
                return result
            sleep(0.2)
        result["status"] = "no_go_user_timer_did_not_fire_within_budget"
        return result
    except (OSError, ValueError, TypeError):
        result["status"] = "no_go_sandbox_setup_failed"
        return result
    finally:
        if scratch is not None and _private_sandbox(scratch):
            shutil.rmtree(scratch)


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) >= 2 else ""
    if mode in {"--fire", "--controller"} and len(sys.argv) == 3:
        status = timer_fire(sys.argv[2]) if mode == "--fire" else controller_crash(
            sys.argv[2]
        )
        sys.exit(status)
    if mode == "--exercise" and len(sys.argv) == 2:
        try:
            report = exercise(runner_temp=os.environ.get("RUNNER_TEMP", ""))
        except Exception:
            report = {
                "status": "no_go_unexpected_canary_exception",
                "real_service_stop_start_restart_performed": False,
                "geniex_or_myai_modified": False,
                "persistent_system_rollback_installed": False,
                "runner_disconnect_or_reboot_recovery_verified": False,
                "npu_or_qnn_executed": False,
            }
        print("MYAI_HTP_LOCAL_RECOVERY_CANARY_JSON=" +
              json.dumps(report, sort_keys=True))
    else:
        sys.exit(2)
