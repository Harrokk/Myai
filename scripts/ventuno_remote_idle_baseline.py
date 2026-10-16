"""Non-invasive, sanitized idle baseline for future performance comparisons.

Reads existing numeric sysfs/proc counters via ventuno_readonly_probe.
Does not stress CPU/NPU, run inference, open audio or alter governor.
Never fabricate a missing temperature or measured response latency.
"""
import json
import math


def _number(value, *, minimum=0, maximum=1000000):
    return (
        value if type(value) in (int, float)
        and math.isfinite(value) and minimum <= value <= maximum
        else None
    )


def summarize(readonly):
    data = readonly if isinstance(readonly, dict) else {}
    mem = data.get("memory") if isinstance(data.get("memory"), dict) else {}
    therm = data.get("thermal") if isinstance(data.get("thermal"), dict) else {}
    freq = data.get("cpu_frequencies") if isinstance(data.get("cpu_frequencies"), dict) else {}
    disk = data.get("root_disk") if isinstance(data.get("root_disk"), dict) else {}
    services = data.get("services") if isinstance(data.get("services"), dict) else {}
    audio = data.get("usb_audio") if isinstance(data.get("usb_audio"), dict) else {}
    return {
        "status": "read-only-idle-baseline",
        "ram_available_gib": _number(mem.get("available_gib"), maximum=1000),
        "disk_available_gib": _number(disk.get("available_gib"), maximum=100000),
        "thermal_sensor_count": _number(therm.get("sensor_count"), maximum=128),
        "temperature_max_c": _number(therm.get("max_c"), minimum=-20, maximum=140),
        "cpu_clock_sample_count": _number(freq.get("sampled_cores"), maximum=64),
        "cpu_clock_min_mhz": _number(freq.get("min_mhz"), maximum=15000),
        "cpu_clock_max_mhz": _number(freq.get("max_mhz"), maximum=15000),
        "usb_audio_present": audio.get("usb_audio_present") is True,
        "myai_service_active": services.get("myai") == "active",
        "geniex_service_active": services.get("geniex") == "active",
        "runner_service_active": services.get("github_runner") == "active",
        "under_load_measurement_performed": False,
        "inference_latency_ms": None,
        "npu_utilization_percent": None,
        "throttling_determined": False,
        "thermal_limits_verified": False,
        "microphone_opened": False,
        "services_modified": False,
    }


def main():
    try:
        from scripts.ventuno_readonly_probe import report
        data = report()
    except Exception:
        data = {}
    print("MYAI_VENTUNO_IDLE_BASELINE_JSON=" + json.dumps(
        summarize(data), sort_keys=True,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
