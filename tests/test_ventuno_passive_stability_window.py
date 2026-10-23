"""Synthetic-only: no actual board, model, audio, systemd or hardware use."""
from copy import deepcopy

from scripts.ventuno_passive_stability_window import summarize


def point(*, temp=40.0, oom=0, restart=0, start=123456, active=True):
    units = {
        n: {
            "metadata_valid": True,
            "restart_counter": restart,
            "main_start_us": start,
            "active": active,
            "loaded": True,
            "enabled_on_boot": True,
            "restart_policy": "disabled" if n == "runner" else "configured",
            "last_result": "success",
            "raw_secret": "NOT_FOR_EXPORT",
        } for n in ("myai", "geniex", "runner")
    }
    return {
        "system": {
            "units": units,
            "cgroups": {
                n: {"oom_kill": oom} for n in ("myai", "geniex")
            },
            "pressure": {
                r: {"some_avg10": 0.2, "some_total_us": 42}
                for r in ("cpu", "memory", "io")
            },
            "mem_gib": 12.1,
            "disk": {
                "root_free_gib": 27.95,
                "root_free_inode_percent": 90.75,
            },
            "SECRET_ENV": "PRIVATE_API_KEY",
        },
        "thermal": {
            "max_c": temp, "sensor_count": 48, "raw_sensor_id": "SERIAL",
        },
    }


def seven():
    return [point() for _ in range(7)]


def test_healthy_longer_window_is_passive_not_reboot_or_recovery_proof():
    report = summarize(seven(), 120)
    assert report["status"] == "no-service-disruption-observed-in-bounded-window"
    assert report["samples"] == 7
    assert report["elapsed_seconds"] == 120.0
    assert report["units"]["runner"]["restart_policy_at_final_sample"] == "disabled"
    assert report["units"]["geniex"]["restarts_observed_from_counter"] == 0
    assert report["service_oom_kill_counter_deltas"] == {"myai": 0, "geniex": 0}
    assert report["continuous_service_availability_proven"] is False
    assert report["reboot_or_reconnect_tested"] is False
    assert report["fault_injection_or_recovery_tested"] is False


def test_short_or_missing_window_must_not_claim_success():
    assert summarize(seven(), 45)["status"] != "no-service-disruption-observed-in-bounded-window"
    assert summarize(seven()[:5], 120)["status"] != "no-service-disruption-observed-in-bounded-window"
    assert summarize([], 0)["status"] == "incomplete-or-warning-in-bounded-window"


def test_real_restart_observed_even_when_currently_active():
    data = seven()
    data[4]["system"]["units"]["myai"]["main_start_us"] = 777777
    out = summarize(data, 120)
    assert out["status"] == "incomplete-or-warning-in-bounded-window"
    assert out["units"]["myai"]["same_main_start_and_restart_counter_all_samples"] is False


def test_oom_increase_is_warning_not_success():
    data = seven()
    data[-1]["system"]["cgroups"]["geniex"]["oom_kill"] = 1
    out = summarize(data, 120)
    assert out["service_oom_kill_counter_deltas"]["geniex"] == 1
    assert out["status"] == "incomplete-or-warning-in-bounded-window"


def test_missing_or_reversed_oom_counter_is_unknown():
    data = seven()
    data[0]["system"]["cgroups"]["myai"]["oom_kill"] = 3
    out = summarize(data, 120)
    assert out["service_oom_kill_counter_deltas"]["myai"] is None
    assert out["status"] != "no-service-disruption-observed-in-bounded-window"


def test_hot_sensor_and_missing_sensor_are_not_silently_okay():
    hot = seven()
    hot[2]["thermal"]["max_c"] = 90.1
    assert summarize(hot, 120)["status"] == "incomplete-or-warning-in-bounded-window"
    missing = seven()
    missing[3]["thermal"]["sensor_count"] = 0
    out = summarize(missing, 120)
    assert out["max_temperature_observed_c"] is None
    assert out["status"] == "incomplete-or-warning-in-bounded-window"


def test_low_memory_and_disk_not_green():
    low_ram = seven()
    low_ram[2]["system"]["mem_gib"] = 1.6
    assert summarize(low_ram, 120)["status"] != "no-service-disruption-observed-in-bounded-window"
    low_disk = seven()
    low_disk[1]["system"]["disk"]["root_free_gib"] = 2.5
    assert summarize(low_disk, 120)["status"] != "no-service-disruption-observed-in-bounded-window"


def test_secrets_ids_and_raw_logs_not_exported():
    data = seven()
    data[1]["system"]["raw_journal"] = "secret-password"
    data[0]["thermal"]["mac"] = "PRIVATE_MAC"
    result = summarize(data, 120)
    text = repr(result)
    for secret in ("NOT_FOR_EXPORT", "PRIVATE_API_KEY", "secret-password", "SERIAL", "PRIVATE_MAC"):
        assert secret not in text
    assert result["microphone_speaker_camera_bluetooth_opened"] is False
    assert result["production_data_written"] is False
    assert result["new_model_inference_executed"] is False


def test_pressure_series_max_is_bounded_and_numeric():
    points = seven()
    points[3]["system"]["pressure"]["cpu"]["some_avg10"] = 4.2
    out = summarize(points, 120)
    assert out["max_cpu_memory_io_psi_some_avg10_percent"]["cpu"] == 4.2
    points[3]["system"]["pressure"]["cpu"]["some_avg10"] = "PRIVATE_TEXT"
    assert summarize(points, 120)["max_cpu_memory_io_psi_some_avg10_percent"]["cpu"] is None


def test_corrupt_units_cannot_be_called_stable():
    pts = seven()
    pts[3]["system"]["units"]["runner"]["restart_counter"] = None
    out = summarize(pts, 120)
    assert out["status"] == "incomplete-or-warning-in-bounded-window"
    assert out["units"]["runner"]["same_main_start_and_restart_counter_all_samples"] is None
