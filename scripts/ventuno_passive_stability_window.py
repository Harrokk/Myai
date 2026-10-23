"""Seven passive host snapshots; no tests are run on production services.

Uses previously reviewed read-only metadata from systemd/proc/sysfs.
No microphone, NPU, Bluetooth, camera, process management or disk writes.
"""
from __future__ import annotations

import json
import math
import time

from scripts.ventuno_readonly_probe import temperature
from scripts.ventuno_service_resilience_readonly import snapshot as system_snapshot

EXPECTED_SAMPLES = 7
INTERVAL_SECONDS = 20
UNIT_NAMES = ("myai", "geniex", "runner")


def finite(value, low=0.0, high=1_000_000.0):
    return (
        float(value) if type(value) in (float, int)
        and math.isfinite(value) and low <= value <= high else None
    )


def readings(sample):
    return sample if isinstance(sample, dict) else {}


def collect():
    return {"system": system_snapshot(), "thermal": temperature()}


def summarize(samples, observed_seconds):
    """Finite allowlisted aggregations only; missing metrics never become zero."""
    samples = samples if isinstance(samples, list) else []
    valid_count = len(samples)
    systems = [readings(readings(row).get("system")) for row in samples]
    thermals = [readings(readings(row).get("thermal")) for row in samples]

    service_details = {}
    for name in UNIT_NAMES:
        units = [readings(readings(s.get("units")).get(name)) for s in systems]
        complete = bool(units) and all(
            unit.get("metadata_valid") is True and
            type(unit.get("restart_counter")) is int and
            type(unit.get("main_start_us")) is int and
            unit["main_start_us"] > 0
            for unit in units
        )
        active_all = bool(units) and all(
            unit.get("active") is True for unit in units
        )
        stable = (
            len({u["main_start_us"] for u in units}) == 1 and
            len({u["restart_counter"] for u in units}) == 1 and
            active_all
        ) if complete else None
        service_details[name] = {
            "active_all_samples": active_all,
            "loaded_at_final_sample": units[-1].get("loaded") is True
                if units else False,
            "enabled_on_boot_at_final_sample":
                units[-1].get("enabled_on_boot") is True if units else False,
            "restart_policy_at_final_sample":
                units[-1].get("restart_policy", "unknown")
                if units else "unknown",
            "same_main_start_and_restart_counter_all_samples": stable,
            "restarts_observed_from_counter": (
                units[-1]["restart_counter"] - units[0]["restart_counter"]
                if complete and units[-1]["restart_counter"] >= units[0]["restart_counter"]
                else None
            ),
            "last_systemd_result":
                units[-1].get("last_result", "unknown")
                if units else "unknown",
        }

    def observed_series(fn, *, low=0, high=1_000_000):
        vals = [finite(fn(x), low, high) for x in systems]
        return vals if vals and all(x is not None for x in vals) else None

    memory_vals = observed_series(lambda x: x.get("mem_gib"), high=256)
    disk_vals = observed_series(
        lambda x: readings(x.get("disk")).get("root_free_gib"), high=65536
    )
    inode_vals = observed_series(
        lambda x: readings(x.get("disk")).get("root_free_inode_percent"),
        high=100,
    )
    temp_vals = [
        finite(x.get("max_c"), -20, 140)
        if type(x.get("sensor_count")) is int and x["sensor_count"] > 0
        else None
        for x in thermals
    ]
    temperatures = (
        temp_vals if temp_vals and all(x is not None for x in temp_vals)
        else None
    )
    pressures = {}
    for category in ("cpu", "memory", "io"):
        values = observed_series(
            lambda x: readings(readings(x.get("pressure")).get(category)).get(
                "some_avg10"
            ),
            high=100,
        )
        pressures[category] = round(max(values), 2) if values else None

    oom = {}
    for name in ("myai", "geniex"):
        values = observed_series(
            lambda x: readings(readings(x.get("cgroups")).get(name)).get(
                "oom_kill"
            ),
            high=100_000_000,
        )
        oom[name] = (
            int(values[-1] - values[0])
            if values and values[-1] >= values[0] else None
        )

    span = finite(observed_seconds, 0, 86400)
    services_ok = all(
        service_details[n]["same_main_start_and_restart_counter_all_samples"] is True
        for n in UNIT_NAMES
    )
    no_oom = all(oom[name] == 0 for name in ("myai", "geniex"))
    safe_observed = (
        valid_count == EXPECTED_SAMPLES and span is not None and span >= 110
        and services_ok and no_oom
        and memory_vals is not None and min(memory_vals) >= 2
        and disk_vals is not None and min(disk_vals) >= 5
        and temperatures is not None and max(temperatures) < 85
    )
    return {
        "status": (
            "no-service-disruption-observed-in-bounded-window"
            if safe_observed else "incomplete-or-warning-in-bounded-window"
        ),
        "samples": valid_count,
        "elapsed_seconds": round(span, 1) if span is not None else None,
        "units": service_details,
        "host_available_memory_min_gib": (
            round(min(memory_vals), 2) if memory_vals else None
        ),
        "root_free_disk_min_gib": (
            round(min(disk_vals), 2) if disk_vals else None
        ),
        "root_free_inodes_min_percent": (
            round(min(inode_vals), 2) if inode_vals else None
        ),
        "max_temperature_observed_c": (
            round(max(temperatures), 2) if temperatures else None
        ),
        "max_cpu_memory_io_psi_some_avg10_percent": pressures,
        "service_oom_kill_counter_deltas": oom,
        "continuous_service_availability_proven": False,
        "reboot_or_reconnect_tested": False,
        "fault_injection_or_recovery_tested": False,
        "cpu_storage_gpu_npu_stressed": False,
        "microphone_speaker_camera_bluetooth_opened": False,
        "new_model_inference_executed": False,
        "service_or_config_modified": False,
        "production_data_written": False,
        "process_ids_or_logs_exported": False,
    }


def main():
    series = []
    start = time.monotonic()
    try:
        for sample_index in range(EXPECTED_SAMPLES):
            if sample_index:
                # Monotonic cadence bounds drift without spawning threads/jobs.
                remaining = start + sample_index * INTERVAL_SECONDS - time.monotonic()
                if remaining > 0:
                    time.sleep(remaining)
            series.append(collect())
        result = summarize(series, time.monotonic() - start)
    except Exception:
        result = summarize(series, time.monotonic() - start)
        result["status"] = "incomplete-or-warning-in-bounded-window"
    print("MYAI_VENTUNO_PASSIVE_STABILITY_WINDOW_JSON=" +
          json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
