"""Staged, fail-closed SYSTEM systemd HTP restoration handler.

NOT INSTALLED OR INVOKED BY CI. This script can act on real services
ONLY if a future, separately approved privileged deployment executes
--restore as root AND a root-owned 0600 lease exists under a root-owned
0700 /run directory. The lease must match this boot ID and be unexpired,
with exactly the three fixed known service names. It may only START
services that were active before the maintenance; it NEVER stops or
restarts a running service, executes shell, alters runner, or loads QNN.

This file does not create/arm the lease or deploy systemd units. That
must be reviewed as a separate, root-owned maintenance implementation
after recovery watchdog design, model/HW safety, operator consent and
release/rollback checks are complete.

No claim this handler already survived a runner outage or a board reboot.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
import time

RESTORE_ORDER = (
    "myai-geniex.service",
    "myai-ventuno.service",
    "myai-geniex-watchdog.service",
)
LEASE_ROOT = Path("/run/myai-htp-restore")
LEASE_FILE = LEASE_ROOT / "lease.json"
BOOT_ID = Path("/proc/sys/kernel/random/boot_id")
MAX_LEASE_BYTES = 1536
LEASE_KEYS = frozenset({
    "schema", "boot_id", "issued_at", "expires_at",
    "restore_units", "armed",
})
BOOT_PATTERN = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
)


def inspect_lease(data, boot, now):
    """Pure validation, no unit or privileged action."""
    if not isinstance(data, dict) or set(data) != LEASE_KEYS:
        return "no_go_invalid_lease_keys"
    if type(data["schema"]) is not int or data["schema"] != 1:
        return "no_go_invalid_lease_schema"
    if data["armed"] is not True:
        return "no_go_lease_not_armed"
    if not isinstance(boot, str) or not BOOT_PATTERN.fullmatch(boot):
        return "no_go_current_boot_identity_unverified"
    if data["boot_id"] != boot:
        return "no_go_boot_identity_changed"
    if (type(data["restore_units"]) is not list or
            data["restore_units"] != list(RESTORE_ORDER)):
        return "no_go_unapproved_service_target"
    issued, expires = data["issued_at"], data["expires_at"]
    if type(issued) not in (int, float) or type(expires) not in (int, float):
        return "no_go_invalid_lease_clock"
    if type(now) not in (int, float):
        return "no_go_invalid_lease_clock"
    # Only a short, bounded monotonic wall-time window, anchored to
    # this boot's immutable UUID (no restoration across reboot).
    if not (0 < expires - issued <= 300 and issued <= now <= expires
            and now - issued <= 300):
        return "no_go_stale_or_future_lease"
    return "lease_valid_for_this_boot_only"


def read_root_lease(directory=LEASE_ROOT, path=LEASE_FILE):
    """Only accept uid-0 controlled, nonsymlinked 0700 dir / 0600 file."""
    try:
        folder = directory.lstat()
        item = path.lstat()
        if not (
            stat.S_ISDIR(folder.st_mode) and folder.st_uid == 0
            and stat.S_IMODE(folder.st_mode) == 0o700
            and stat.S_ISREG(item.st_mode) and item.st_uid == 0
            and stat.S_IMODE(item.st_mode) == 0o600
            and item.st_nlink == 1
            and path.parent == directory
        ):
            return None, None
        flags = os.O_RDONLY
        if hasattr(os, "O_NOFOLLOW"):
            flags |= os.O_NOFOLLOW
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb") as file:
            opened = os.fstat(file.fileno())
            if (opened.st_ino, opened.st_dev) != (item.st_ino, item.st_dev):
                return None, None
            raw = file.read(MAX_LEASE_BYTES + 1)
        if len(raw) > MAX_LEASE_BYTES:
            return None, None
        data = json.loads(raw.decode("utf-8"))
        return data, (item.st_dev, item.st_ino)
    except (OSError, UnicodeError, ValueError, TypeError):
        return None, None


def safe_command(args, timeout=12):
    """Never print or return service messages or unbounded process logs."""
    try:
        task = subprocess.run(
            list(args), capture_output=True, check=False, timeout=timeout,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        return task.returncode == 0
    except (OSError, subprocess.TimeoutExpired, ValueError):
        return False


def restore_under_validated_lease(*, lease, boot_id, now, command,
                                  current_is_root, lease_identity_valid):
    """Injectable simulator/executor; actions only after every strict gate."""
    result = {
        "probe": "ventuno_htp_system_recovery_staged",
        "status": "no_go",
        "valid_lease_on_current_boot": False,
        "service_start_attempts": 0,
        "all_required_services_active_afterward": False,
        "runner_service_touched": False,
        "any_service_stopped_or_restarted": False,
        "qnn_or_htp_executed": False,
        "privileged_service_action_attempted": False,
        "recovery_command_executed": False,
        "lease_or_boot_identity_exported": False,
        "private_process_logs_exported": False,
    }
    if current_is_root is not True or lease_identity_valid is not True:
        result["status"] = "no_go_root_owned_lease_not_attested"
        return result
    reason = inspect_lease(lease, boot_id, now)
    if reason != "lease_valid_for_this_boot_only":
        result["status"] = reason
        return result
    result["valid_lease_on_current_boot"] = True
    failed = False
    for unit in RESTORE_ORDER:
        # is-active is safe. A previously running unit must not be
        # unnecessarily restarted or killed.
        active = command(
            ("systemctl", "is-active", "--quiet", unit)
        )
        if not active:
            result["service_start_attempts"] += 1
            result["privileged_service_action_attempted"] = True
            result["recovery_command_executed"] = True
            if not command(("systemctl", "start", unit)):
                failed = True
        if not command(("systemctl", "is-active", "--quiet", unit)):
            failed = True
    result["all_required_services_active_afterward"] = not failed
    result["status"] = (
        "restoration_verified_on_original_three_services"
        if not failed else "recovery_incomplete_manual_intervention_required"
    )
    return result


def run_root_handler():
    if os.geteuid() != 0:
        return restore_under_validated_lease(
            lease=None, boot_id=None, now=None,
            command=lambda args: False,
            current_is_root=False, lease_identity_valid=False,
        )
    doc, identity = read_root_lease()
    try:
        boot = BOOT_ID.read_text(encoding="ascii").strip()
    except OSError:
        boot = ""
    report = restore_under_validated_lease(
        lease=doc, boot_id=boot, now=time.time(),
        command=safe_command,
        current_is_root=True,
        lease_identity_valid=identity is not None,
    )
    # A real service start can be reported as completed without deleting
    # the lease: leaving root-owned evidence avoids an unsafe rearm race
    # until a separate reviewed maintenance finalizer cleans it.
    return report


if __name__ == "__main__":
    if sys.argv[1:] != ["--restore"]:
        sys.exit(2)
    try:
        report = run_root_handler()
    except Exception:
        report = {
            "status": "no_go_unexpected_restore_exception",
            "runner_service_touched": False,
            "qnn_or_htp_executed": False,
            "private_process_logs_exported": False,
        }
    print("MYAI_HTP_STAGED_SYSTEM_RECOVERY_JSON=" + json.dumps(
        report, sort_keys=True
    ))
    sys.exit(
        0 if report["status"] == "restoration_verified_on_original_three_services"
        else 1
    )
