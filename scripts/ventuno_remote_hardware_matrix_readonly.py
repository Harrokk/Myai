"""Two-pass unattended VENTUNO metadata only; no device streams or load.

Imports vetted read-only inventory; it does not open microphone, Bluetooth,
NPU/FastRPC, camera, sound or storage test files. Never prints identifiers.
"""
from __future__ import annotations

import json
import math
import time
from collections.abc import Mapping


def finite_number(value, minimum, maximum):
    if (type(value) not in (int, float) or not math.isfinite(value)
            or not minimum <= value <= maximum):
        return None
    return round(float(value), 2)


def nonnegative_int(value, maximum=100000):
    return value if type(value) is int and 0 <= value <= maximum else None


def section(data, name):
    part = data.get(name) if isinstance(data, Mapping) else None
    return part if isinstance(part, Mapping) else {}


def summarize(before, after):
    """Build allowlisted anonymous measurements; no raw host strings."""
    a, b = before if isinstance(before, Mapping) else {}, (
        after if isinstance(after, Mapping) else {}
    )
    platform = section(b, "platform")
    memory = section(b, "memory")
    disk = section(b, "root_disk")
    temp0, temp1 = section(a, "thermal"), section(b, "thermal")
    freq = section(b, "cpu_frequencies")
    usb = section(b, "usb_audio")
    network = section(b, "network")
    pcm = section(b, "pcm_capabilities")
    accelerators = section(b, "accelerator_indicators_only")
    qcom = section(b, "qualcomm_runtime_indicators_only")
    services0, services1 = section(a, "services"), section(b, "services")

    first_temp = finite_number(temp0.get("max_c"), -20, 140)
    second_temp = finite_number(temp1.get("max_c"), -20, 140)
    temp_change = (round(second_temp-first_temp, 2)
                   if first_temp is not None and second_temp is not None
                   else None)
    both_services = all(
        services.get(name) == "active"
        for services in (services0, services1)
        for name in ("myai", "geniex")
    )
    available_mem = finite_number(memory.get("available_gib"), 0, 128)
    free_disk = finite_number(disk.get("available_gib"), 0, 65536)

    return {
        "status": ("passive-hardware-metadata-recorded"
                   if both_services else "passive-inventory-service-state-inconclusive"),
        "actual_board_snapshots": 2,
        "cpu_logical_cores": nonnegative_int(platform.get("logical_cpus"), 256),
        "cpu_current_freq_sampled_cores": nonnegative_int(freq.get("sampled_cores"), 256),
        "cpu_current_min_mhz": nonnegative_int(freq.get("min_mhz"), 16000),
        "cpu_current_max_mhz": nonnegative_int(freq.get("max_mhz"), 16000),
        "uptime_hours": finite_number(platform.get("uptime_hours"), 0, 100000),
        "ram_total_gib": finite_number(memory.get("total_gib"), 0, 128),
        "ram_available_gib": available_mem,
        "swap_total_gib": finite_number(memory.get("swap_total_gib"), 0, 2048),
        "root_disk_total_gib": finite_number(disk.get("total_gib"), 0, 65536),
        "root_disk_available_gib": free_disk,
        "ram_at_least_4gib": available_mem is not None and available_mem >= 4,
        "disk_at_least_5gib": free_disk is not None and free_disk >= 5,
        "thermal_sensor_count": nonnegative_int(temp1.get("sensor_count"), 256),
        "thermal_first_max_c": first_temp,
        "thermal_second_max_c": second_temp,
        "thermal_observed_max_delta_c": temp_change,
        "thermal_high_85c_observed": bool(
            (first_temp is not None and first_temp >= 85)
            or (second_temp is not None and second_temp >= 85)
        ),
        "usb_physical_device_count": nonnegative_int(usb.get("usb_device_count"), 128),
        "usb_audio_card_count": nonnegative_int(usb.get("usb_audio_card_count"), 32),
        "alsa_capture_pcm_count": nonnegative_int(pcm.get("alsa_capture_pcm_count"), 128),
        "alsa_playback_pcm_count": nonnegative_int(pcm.get("alsa_playback_pcm_count"), 128),
        "wifi_interface_count": nonnegative_int(network.get("wifi_interface_count"), 16),
        "wifi_links_up": nonnegative_int(network.get("wifi_link_up_count"), 16),
        "ethernet_interface_count": nonnegative_int(network.get("ethernet_interface_count"), 16),
        "bluetooth_hci_count": nonnegative_int(network.get("bluetooth_hci_count"), 16),
        "gpu_render_node_count": nonnegative_int(accelerators.get("gpu_render_nodes"), 16),
        "fastrpc_device_node_count": nonnegative_int(qcom.get("fastrpc_device_nodes"), 16),
        "remoteproc_running_count": nonnegative_int(qcom.get("remote_processors_running"), 32),
        "qnn_htp_library_in_standard_paths":
            qcom.get("qnn_htp_library_in_standard_paths") is True,
        "myai_service_active_both_snapshots": all(
            services.get("myai") == "active"
            for services in (services0, services1)
        ),
        "geniex_service_active_both_snapshots": all(
            services.get("geniex") == "active"
            for services in (services0, services1)
        ),
        "bluetooth_pairing_performed": False,
        "wifi_discovery_performed": False,
        "network_throughput_tested": False,
        "usb_streams_opened": False,
        "camera_streams_opened": False,
        "microphone_opened": False,
        "speaker_opened": False,
        "cpu_stress_tested": False,
        "storage_rw_benchmarked": False,
        "npu_inference_tested": False,
        "thermal_throttling_verified": False,
        "production_modified": False,
    }


def main():
    from scripts.ventuno_readonly_probe import report
    try:
        first = report()
        time.sleep(3)
        second = report()
        result = summarize(first, second)
    except Exception:
        result = summarize({}, {})
        result["status"] = "passive-inventory-incomplete"
    print("MYAI_REMOTE_HARDWARE_MATRIX_JSON="+json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
