"""VENTUNO service reliability status: two passive snapshots, never a restart.

All returned data are bounded, allowlisted, non-identifying values. Reads only
named systemd properties and proc/cgroup counters, not journal or service logs.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import subprocess
import time

UNITS = {
    "myai": "myai-ventuno.service",
    "geniex": "myai-geniex.service",
    "runner": "actions.runner.Harrokk-Myai.ventuno-q.service",
}
PROPS = (
    "LoadState", "ActiveState", "UnitFileState", "Restart",
    "NRestarts", "ExecMainStartTimestampMonotonic", "Result",
)
RESTART_MODES = frozenset(
    ("always", "on-failure", "on-abnormal", "on-watchdog", "on-abort")
)
MAX_SYSTEMD_BYTES = 3072
SYSTEMCTL_ENV = {"LC_ALL": "C", "PATH": "/usr/bin:/bin"}


def bounded_file(path, limit=16384):
    try:
        with open(path, "rb") as f:
            raw = f.read(limit + 1)
        return raw.decode("ascii") if len(raw) <= limit else None
    except (OSError, UnicodeError, ValueError):
        return None


def integer(value, maximum=10**14):
    if isinstance(value, str) and re.fullmatch(r"[0-9]{1,16}", value):
        n = int(value)
        return n if n <= maximum else None
    return None


def unit_properties(raw):
    """Return allowlisted states; malformed output never gets a green check."""
    empty = {
        "loaded": False, "active": False, "enabled_on_boot": False,
        "restart_policy": "unknown", "restart_counter": None,
        "main_start_us": None, "last_result": "unknown",
        "metadata_valid": False,
    }
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_SYSTEMD_BYTES:
        return empty
    attrs = {}
    for line in raw.splitlines():
        key, sep, value = line.partition("=")
        if not sep or key not in PROPS or key in attrs:
            return empty
        attrs[key] = value.strip()
    if set(attrs) != set(PROPS):
        return empty
    restart = attrs["Restart"]
    result = attrs["Result"]
    return {
        "loaded": attrs["LoadState"] == "loaded",
        "active": attrs["ActiveState"] == "active",
        "enabled_on_boot": attrs["UnitFileState"] == "enabled",
        "restart_policy": (
            "configured" if restart in RESTART_MODES
            else "disabled" if restart == "no" else "unknown"
        ),
        "restart_counter": integer(attrs["NRestarts"], 1_000_000),
        "main_start_us": integer(attrs["ExecMainStartTimestampMonotonic"]),
        "last_result": (
            "success" if result == "success" else
            "failure_observed" if result in {
                "exit-code", "signal", "core-dump", "watchdog",
                "timeout", "oom-kill", "resources", "start-limit-hit",
            } else "unknown"
        ),
        "metadata_valid": True,
    }


def unit_read(name, runner=subprocess.run):
    args = ["systemctl", "show", UNITS[name], "--no-pager",
            "--property=" + ",".join(PROPS)]
    try:
        result = runner(
            args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            check=False, timeout=5, env=SYSTEMCTL_ENV,
        )
        if result.returncode != 0 or len(result.stdout) > MAX_SYSTEMD_BYTES:
            return unit_properties(None)
        return unit_properties(result.stdout.decode("ascii", "strict"))
    except (OSError, subprocess.TimeoutExpired, UnicodeError, ValueError):
        return unit_properties(None)


def memory_events(name):
    # Exact named systemd cgroup v2 paths only: no recursive inspection.
    raw = bounded_file(
        "/sys/fs/cgroup/system.slice/" + UNITS[name] + "/memory.events", 4096
    )
    if raw is None:
        return {"oom": None, "oom_kill": None, "high": None}
    entries = {}
    for row in raw.splitlines():
        pair = row.split()
        if len(pair) != 2 or pair[0] in entries:
            return {"oom": None, "oom_kill": None, "high": None}
        entries[pair[0]] = integer(pair[1])
    return {key: entries.get(key) for key in ("oom", "oom_kill", "high")}


def psi(path):
    raw = bounded_file(path, 2048)
    empty = {"some_avg10": None, "some_total_us": None}
    if raw is None:
        return empty
    for line in raw.splitlines():
        bits = line.split()
        if not bits or bits[0] != "some":
            continue
        fields = {}
        for item in bits[1:]:
            k, sep, value = item.partition("=")
            if sep and k in ("avg10", "total") and k not in fields:
                fields[k] = value
        try:
            value = float(fields.get("avg10", "nan"))
            total = integer(fields.get("total", ""))
            if not math.isfinite(value) or not 0 <= value <= 100:
                return empty
            return {"some_avg10": round(value, 2), "some_total_us": total}
        except (ValueError, TypeError):
            return empty
    return empty


def available_memory_gib():
    raw = bounded_file("/proc/meminfo", 16384)
    if raw is None:
        return None
    for line in raw.splitlines():
        match = re.fullmatch(r"MemAvailable:\s+(\d{1,16})\s+kB", line)
        if match:
            kib = integer(match.group(1))
            return round(kib / 1048576, 2) if kib is not None else None
    return None


def root_headroom():
    try:
        v = os.statvfs("/")
        gib = round(v.f_bavail * v.f_frsize / 1073741824, 2)
        inode_free_ratio = (
            round(100 * v.f_favail / v.f_files, 2)
            if v.f_files > 0 else None
        )
        return {"root_free_gib": gib,
                "root_free_inode_percent": inode_free_ratio}
    except (OSError, ValueError, ZeroDivisionError):
        return {"root_free_gib": None, "root_free_inode_percent": None}


def snapshot():
    return {
        "units": {name: unit_read(name) for name in UNITS},
        "cgroups": {
            name: memory_events(name) for name in ("myai", "geniex")
        },
        "pressure": {
            resource: psi("/proc/pressure/" + resource)
            for resource in ("cpu", "memory", "io")
        },
        "mem_gib": available_memory_gib(),
        "disk": root_headroom(),
    }


def delta(a, b):
    return b - a if type(a) is int and type(b) is int and 0 <= a <= b else None


def summarize(before, after):
    a = before if isinstance(before, dict) else {}
    b = after if isinstance(after, dict) else {}
    ua = a.get("units") if isinstance(a.get("units"), dict) else {}
    ub = b.get("units") if isinstance(b.get("units"), dict) else {}
    ca = a.get("cgroups") if isinstance(a.get("cgroups"), dict) else {}
    cb = b.get("cgroups") if isinstance(b.get("cgroups"), dict) else {}
    pa = a.get("pressure") if isinstance(a.get("pressure"), dict) else {}
    pb = b.get("pressure") if isinstance(b.get("pressure"), dict) else {}
    disk = b.get("disk") if isinstance(b.get("disk"), dict) else {}

    units = {}
    for name in UNITS:
        prev = ua.get(name) if isinstance(ua.get(name), dict) else {}
        curr = ub.get(name) if isinstance(ub.get(name), dict) else {}
        nprev = prev.get("restart_counter")
        ncurr = curr.get("restart_counter")
        start_prev = prev.get("main_start_us")
        start_curr = curr.get("main_start_us")
        comparable = (
            type(nprev) is int and type(ncurr) is int
            and type(start_prev) is int and type(start_curr) is int
            and start_prev > 0 and start_curr > 0
        )
        stable = (
            comparable and nprev == ncurr and start_prev == start_curr
            and prev.get("active") is True and curr.get("active") is True
        )
        restart_change = delta(nprev, ncurr)
        units[name] = {
            "loaded": curr.get("loaded") is True,
            "active_both_snapshots": (
                prev.get("active") is True and curr.get("active") is True
            ),
            "enabled_on_boot": curr.get("enabled_on_boot") is True,
            "restart_policy": curr.get("restart_policy", "unknown"),
            "restart_count_since_last_unit_reset": (
                ncurr if type(ncurr) is int else None
            ),
            "restart_count_delta": restart_change,
            "same_main_start_and_no_restart_observed":
                stable if comparable else None,
            "last_systemd_result": curr.get("last_result", "unknown"),
            "metadata_valid_both": (
                prev.get("metadata_valid") is True and
                curr.get("metadata_valid") is True
            ),
        }
    cgroups = {}
    for name in ("myai", "geniex"):
        old = ca.get(name) if isinstance(ca.get(name), dict) else {}
        new = cb.get(name) if isinstance(cb.get(name), dict) else {}
        cgroups[name] = {
            "oom_kill_total": new.get("oom_kill")
                if type(new.get("oom_kill")) is int else None,
            "oom_kill_delta": delta(old.get("oom_kill"), new.get("oom_kill")),
            "memory_high_delta": delta(old.get("high"), new.get("high")),
        }
    pressure = {}
    for resource in ("cpu", "memory", "io"):
        old = pa.get(resource) if isinstance(pa.get(resource), dict) else {}
        new = pb.get(resource) if isinstance(pb.get(resource), dict) else {}
        v = new.get("some_avg10")
        pressure[resource] = {
            "some_avg10_percent": v if type(v) in (int, float) else None,
            "some_total_delta_us": delta(
                old.get("some_total_us"), new.get("some_total_us")
            ),
        }
    mem = b.get("mem_gib")
    memory_gib = mem if type(mem) in (int, float) and 0 <= mem <= 256 else None
    free_gib = disk.get("root_free_gib")
    disk_gib = (
        free_gib if type(free_gib) in (int, float) and 0 <= free_gib <= 65536
        else None
    )
    inodes = disk.get("root_free_inode_percent")
    inode_pct = (
        inodes if type(inodes) in (int, float) and 0 <= inodes <= 100 else None
    )
    services_ok = all(
        units[name]["active_both_snapshots"]
        for name in ("myai", "geniex", "runner")
    )
    return {
        "status": (
            "passive-service-health-observed" if services_ok and
            memory_gib is not None and memory_gib >= 2 and
            disk_gib is not None and disk_gib >= 5
            else "passive-health-warning-or-incomplete"
        ),
        "snapshots": 2,
        "services": units,
        "cgroup_memory_events": cgroups,
        "host_pressure": pressure,
        "mem_available_gib": memory_gib,
        "disk_available_gib": disk_gib,
        "root_free_inode_percent": inode_pct,
        "reboot_and_auto_reconnect_tested": False,
        "multi_day_availability_tested": False,
        "automatic_recovery_tested": False,
        "real_failure_injected": False,
        "service_restarted_or_reloaded": False,
        "configuration_modified": False,
        "microphone_camera_speaker_bluetooth_opened": False,
        "new_npu_or_model_inference": False,
        "production_write_performed": False,
        "raw_systemd_logs_or_secrets_exported": False,
    }


def main():
    try:
        first = snapshot()
        time.sleep(4)
        second = snapshot()
        answer = summarize(first, second)
    except Exception:
        answer = summarize({}, {})
        answer["status"] = "passive-health-incomplete"
    print("MYAI_VENTUNO_SERVICE_RESILIENCE_JSON=" +
          json.dumps(answer, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
