"""All synthetic: none of these tests import hardware/audio SDKs."""
from scripts.ventuno_remote_hardware_matrix_readonly import summarize


def sample(*, temp=42.0, myai="active", geniex="active"):
    return {
        "platform": {"logical_cpus": 8, "uptime_hours": 65.2, "kernel": "secret-kernel"},
        "memory": {"total_gib": 15.5, "available_gib": 11.1, "swap_total_gib": 0},
        "root_disk": {"total_gib": 55.0, "available_gib": 37.7},
        "thermal": {"sensor_count": 12, "max_c": temp, "min_c": 24.0},
        "cpu_frequencies": {"sampled_cores": 8, "min_mhz": 1000, "max_mhz": 2300},
        "usb_audio": {"usb_device_count": 3, "usb_audio_card_count": 1},
        "pcm_capabilities": {"alsa_capture_pcm_count": 1, "alsa_playback_pcm_count": 1},
        "network": {"wifi_interface_count": 1, "wifi_link_up_count": 1,
                    "ethernet_interface_count": 1, "bluetooth_hci_count": 1,
                    "ssid": "PRIVATE_SSID"},
        "accelerator_indicators_only": {"gpu_render_nodes": 1},
        "qualcomm_runtime_indicators_only": {
            "fastrpc_device_nodes": 2, "remote_processors_running": 2,
            "qnn_htp_library_in_standard_paths": True,
        },
        "services": {"myai": myai, "geniex": geniex},
    }


def test_two_physical_snapshot_summary():
    result = summarize(sample(temp=39), sample(temp=42))
    assert result["status"] == "passive-hardware-metadata-recorded"
    assert result["cpu_logical_cores"] == 8
    assert result["ram_available_gib"] == 11.1
    assert result["thermal_observed_max_delta_c"] == 3
    assert result["wifi_links_up"] == 1
    assert result["bluetooth_hci_count"] == 1
    assert result["fastrpc_device_node_count"] == 2
    assert result["npu_inference_tested"] is False


def test_missing_readings_unknown_never_invent_zeros():
    result = summarize({}, {})
    assert result["status"] == "passive-inventory-service-state-inconclusive"
    assert result["thermal_first_max_c"] is None
    assert result["thermal_second_max_c"] is None
    assert result["ram_available_gib"] is None
    assert result["disk_at_least_5gib"] is False


def test_hot_sensor_warns_observed_threshold_only():
    result = summarize(sample(temp=86), sample(temp=89))
    assert result["thermal_high_85c_observed"] is True
    assert result["thermal_throttling_verified"] is False


def test_service_state_failure_does_not_get_green_status():
    result = summarize(sample(), sample(geniex="inactive"))
    assert result["status"] == "passive-inventory-service-state-inconclusive"
    assert result["myai_service_active_both_snapshots"] is True
    assert result["geniex_service_active_both_snapshots"] is False


def test_no_private_ids_network_settings_or_extra_sensors_in_output():
    result = summarize(sample(), sample())
    output = repr(result)
    for secret in ("PRIVATE_SSID", "secret-kernel", "serial", "mac", "ip_address"):
        assert secret not in output
    assert result["microphone_opened"] is False
    assert result["speaker_opened"] is False
    assert result["camera_streams_opened"] is False
    assert result["production_modified"] is False


def test_bad_numbers_are_not_exported():
    current = sample()
    current["thermal"]["max_c"] = float("nan")
    current["memory"]["available_gib"] = -1
    current["platform"]["logical_cpus"] = True
    result = summarize(sample(), current)
    assert result["thermal_second_max_c"] is None
    assert result["thermal_observed_max_delta_c"] is None
    assert result["ram_available_gib"] is None
    assert result["cpu_logical_cores"] is None
