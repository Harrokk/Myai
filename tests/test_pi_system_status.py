from types import SimpleNamespace

from modules.pi import system_status


def test_parse_throttled_zero_is_ok():
    result = system_status.parse_throttled("throttled=0x0")

    assert result["ok"] is True
    assert result["flags"] == []


def test_parse_throttled_decodes_current_and_historic_flags():
    value = (1 << 0) | (1 << 2) | (1 << 16)
    result = system_status.parse_throttled(f"0x{value:x}")

    assert result["ok"] is False
    assert "underspänning pågår" in result["flags"]
    assert "systemet throttlar" in result["flags"]
    assert "underspänning har inträffat" in result["flags"]


def test_detect_raspberry_pi_from_model_file(monkeypatch):
    monkeypatch.setattr(
        system_status,
        "_read_text",
        lambda path: "Raspberry Pi 5 Model B Rev 1.0",
    )

    detected, model = system_status.detect_raspberry_pi()

    assert detected is True
    assert "Raspberry Pi 5" in model


def test_collect_pi_status_returns_safe_non_pi_result(monkeypatch):
    monkeypatch.setattr(
        system_status,
        "detect_raspberry_pi",
        lambda: (False, "Windows AMD64"),
    )

    result = system_status.collect_pi_status()

    assert result == {
        "is_raspberry_pi": False,
        "model": "Windows AMD64",
    }


def test_collect_pi_status_combines_available_readings(monkeypatch):
    monkeypatch.setattr(
        system_status,
        "detect_raspberry_pi",
        lambda: (True, "Raspberry Pi 5 Model B"),
    )
    monkeypatch.setattr(system_status.psutil, "cpu_percent", lambda interval: 12.5)
    monkeypatch.setattr(system_status.psutil, "cpu_count", lambda logical=True: 4)
    monkeypatch.setattr(
        system_status.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            used=4 * 1024 ** 3,
            total=8 * 1024 ** 3,
            percent=50.0,
        ),
    )
    monkeypatch.setattr(
        system_status.psutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            free=20 * 1024 ** 3,
            total=64 * 1024 ** 3,
            percent=68.8,
        ),
    )
    monkeypatch.setattr(system_status, "read_cpu_temperature", lambda: 52.3)
    monkeypatch.setattr(
        system_status,
        "read_throttling",
        lambda: {
            "raw": 0,
            "hex": "0x0",
            "flags": [],
            "ok": True,
        },
    )
    monkeypatch.setattr(system_status, "read_core_voltage", lambda: 0.91)

    result = system_status.collect_pi_status()

    assert result["is_raspberry_pi"] is True
    assert result["temperature_c"] == 52.3
    assert result["core_voltage_v"] == 0.91
    assert result["throttling"]["ok"] is True


def test_format_pi_status_mentions_missing_hardware_on_non_pi():
    text = system_status.format_pi_status(
        {
            "is_raspberry_pi": False,
            "model": "Windows AMD64",
        }
    )

    assert "upptäcktes inte" in text
    assert "Windows AMD64" in text


def test_format_pi_status_reports_throttling_warning():
    text = system_status.format_pi_status(
        {
            "is_raspberry_pi": True,
            "model": "Raspberry Pi 5 Model B",
            "cpu_percent": 10,
            "cpu_count": 4,
            "ram_used_gb": 2.0,
            "ram_total_gb": 8.0,
            "ram_percent": 25,
            "disk_free_gb": 40.0,
            "disk_total_gb": 64.0,
            "disk_percent": 37.5,
            "temperature_c": 60.0,
            "core_voltage_v": 0.9,
            "throttling": {
                "ok": False,
                "hex": "0x1",
                "flags": ["underspänning pågår"],
            },
        }
    )

    assert "underspänning pågår" in text
    assert "60.0 °C" in text
