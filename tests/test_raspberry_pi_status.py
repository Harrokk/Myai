from types import SimpleNamespace

from modules.raspberry_pi import status


class FakePsutil:
    @staticmethod
    def cpu_percent(interval=0.1):
        assert interval == 0.1
        return 17.5

    @staticmethod
    def virtual_memory():
        return SimpleNamespace(
            used=2 * 1024 ** 3,
            total=8 * 1024 ** 3,
            percent=25.0,
        )

    @staticmethod
    def disk_usage(path):
        assert path == "/"
        return SimpleNamespace(
            free=48 * 1024 ** 3,
            total=64 * 1024 ** 3,
            percent=25.0,
        )


def fake_reader(path):
    values = {
        status.MODEL_PATH: "Raspberry Pi 5 Model B Rev 1.0\x00",
        status.THERMAL_PATH: "42123\n",
    }
    return values[path]


def fake_runner(command, capture_output, text, timeout):
    assert command[0] == "vcgencmd"
    assert capture_output is True
    assert text is True
    assert timeout == 5

    if command[1:] == ["measure_volts", "core"]:
        output = "volt=0.9000V\n"
    elif command[1:] == ["get_throttled"]:
        output = "throttled=0x0\n"
    elif command[1:] == ["measure_temp"]:
        output = "temp=42.1'C\n"
    else:
        raise AssertionError(f"Oväntat kommando: {command}")

    return SimpleNamespace(
        returncode=0,
        stdout=output,
    )


def test_decode_throttled_flags_handles_current_and_historical_bits():
    flags = status.decode_throttled_flags("throttled=0x50005")

    assert "underspänning pågår" in flags
    assert "throttling pågår" in flags
    assert "underspänning har inträffat" in flags
    assert "throttling har inträffat" in flags


def test_get_raspberry_pi_status_collects_core_metrics():
    result = status.get_raspberry_pi_status(
        reader=fake_reader,
        runner=fake_runner,
        psutil_module=FakePsutil,
    )

    assert result["is_raspberry_pi"] is True
    assert result["model"] == "Raspberry Pi 5 Model B Rev 1.0"
    assert result["cpu_percent"] == 17.5
    assert result["ram_total_gb"] == 8.0
    assert result["disk_total_gb"] == 64.0
    assert result["temperature_c"] == 42.1
    assert result["core_voltage_v"] == 0.9
    assert result["throttling_flags"] == []
    assert result["power_w"] is None


def test_format_status_does_not_guess_power_draw():
    result = status.get_raspberry_pi_status(
        reader=fake_reader,
        runner=fake_runner,
        psutil_module=FakePsutil,
    )

    text = status.format_raspberry_pi_status(result)

    assert "Raspberry Pi 5 Model B" in text
    assert "42.1 °C" in text
    assert "0.900 V" in text
    assert "inga flaggor" in text
    assert "ej direkt mätbar utan extern mätkälla" in text


def test_non_pi_system_is_reported_without_false_pi_claims():
    def reader(path):
        if path == status.MODEL_PATH:
            return "Generic ARM Board"
        if path == status.THERMAL_PATH:
            return "40000"
        raise OSError(path)

    result = status.get_raspberry_pi_status(
        reader=reader,
        runner=fake_runner,
        psutil_module=FakePsutil,
    )

    text = status.format_raspberry_pi_status(result)

    assert result["is_raspberry_pi"] is False
    assert "identifierades inte som en Raspberry Pi" in text
