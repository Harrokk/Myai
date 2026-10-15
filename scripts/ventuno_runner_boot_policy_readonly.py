"""Read-only installed GitHub Actions runner boot/reconnect policy check.

No reboot, network activity, login, systemctl start/stop or token access.
Only exact systemd unit metadata is inspected; successful boot reconnect
is NOT established by metadata alone.
"""
from __future__ import annotations

import json
import subprocess

UNIT = "actions.runner.Harrokk-Myai.ventuno-q.service"
PROPS = ("LoadState", "ActiveState", "UnitFileState", "Restart")
MAX_BYTES = 2048


def classify(raw):
    response = {
        "probe": "ventuno_github_runner_boot_policy_readonly",
        "status": "no_go_runner_service_metadata_unverified",
        "runner_unit_loaded": False,
        "runner_service_currently_active": False,
        "runner_persistently_enabled_on_boot": False,
        "runner_systemd_restart_policy_enabled": False,
        "runner_reconnect_after_actual_reboot_verified": False,
        "runner_service_or_network_modified": False,
        "runner_credentials_or_unit_paths_exported": False,
    }
    if not isinstance(raw, bytes) or not 1 <= len(raw) <= MAX_BYTES:
        return response
    try:
        lines = raw.decode("utf-8").splitlines()
        attrs = {}
        for line in lines:
            key, sep, value = line.partition("=")
            if not sep or key not in PROPS or key in attrs:
                return response
            attrs[key] = value
        if set(attrs) != set(PROPS):
            return response
        response["runner_unit_loaded"] = attrs["LoadState"] == "loaded"
        response["runner_service_currently_active"] = attrs["ActiveState"] == "active"
        response["runner_persistently_enabled_on_boot"] = (
            attrs["UnitFileState"] == "enabled"
        )
        response["runner_systemd_restart_policy_enabled"] = (
            attrs["Restart"] in {"always", "on-failure", "on-abnormal"}
        )
        response["status"] = (
            "boot_autostart_configured_not_reboot_verified"
            if (response["runner_unit_loaded"] and
                response["runner_persistently_enabled_on_boot"])
            else "no_go_boot_autostart_not_verified"
        )
        return response
    except UnicodeError:
        return response


def report(executor=subprocess.run):
    args = [
        "systemctl", "show", UNIT, "--no-pager",
        "--property=" + ",".join(PROPS),
    ]
    try:
        result = executor(
            args, capture_output=True, timeout=5, check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
        raw = result.stdout if result.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired, ValueError):
        raw = None
    return classify(raw)


if __name__ == "__main__":
    print("MYAI_RUNNER_BOOT_POLICY_JSON=" + json.dumps(report(), sort_keys=True))
