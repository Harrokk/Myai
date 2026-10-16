"""Pure numeric telemetry baseline tests, no hardware interaction."""
import json

from scripts import ventuno_remote_idle_baseline as mod


def observed():
    return {
        "memory": {"available_gib": 7.3, "private_memory": "SECRET_PATH"},
        "thermal": {"sensor_count": 5, "max_c": 48.7},
        "cpu_frequencies": {
            "sampled_cores": 8, "min_mhz": 600, "max_mhz": 2350,
        },
        "root_disk": {"available_gib": 22.4},
        "services": {
            "myai": "active", "geniex": "active", "github_runner": "active",
            "private_name": "SECRET_SERVICE",
        },
        "usb_audio": {"usb_audio_present": True, "serial": "SECRET_AUDIO_ID"},
        "platform": {"name": "SECRET_HOSTNAME"},
    }


def test_idle_measured_numbers_but_not_unobserved_latency_or_npu_load():
    result = mod.summarize(observed())
    assert result["ram_available_gib"] == 7.3
    assert result["temperature_max_c"] == 48.7
    assert result["cpu_clock_min_mhz"] == 600
    assert result["usb_audio_present"] is True
    assert result["myai_service_active"] is True
    assert result["under_load_measurement_performed"] is False
    assert result["inference_latency_ms"] is None
    assert result["npu_utilization_percent"] is None
    assert result["thermal_limits_verified"] is False
    assert "SECRET" not in json.dumps(result)


def test_unknown_sensors_remain_null_not_zero_or_imaginary():
    result = mod.summarize({})
    assert result["temperature_max_c"] is None
    assert result["ram_available_gib"] is None
    assert result["cpu_clock_max_mhz"] is None
    assert result["throttling_determined"] is False
    assert result["geniex_service_active"] is False


def test_out_of_range_private_and_nan_fields_cannot_escape():
    value = observed()
    value["thermal"]["max_c"] = float("nan")
    value["memory"]["available_gib"] = -999
    value["cpu_frequencies"]["max_mhz"] = 12345678
    value["root_disk"]["available_gib"] = "PRIVATE_DISK"
    result = mod.summarize(value)
    assert result["temperature_max_c"] is None
    assert result["ram_available_gib"] is None
    assert result["cpu_clock_max_mhz"] is None
    assert result["disk_available_gib"] is None
    assert "PRIVATE" not in json.dumps(result)


def test_no_live_io_is_needed_for_synthetic_summary():
    payload = observed()
    result = mod.summarize(payload)
    assert result["microphone_opened"] is False
    assert result["services_modified"] is False
    assert result["status"] == "read-only-idle-baseline"
