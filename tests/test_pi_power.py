from modules.pi import power


def write(path, value):
    path.write_text(str(value), encoding="utf-8")


def test_power_telemetry_is_safe_on_non_linux(monkeypatch):
    monkeypatch.setattr(power.platform, "system", lambda: "Windows")

    result = power.collect_power_telemetry()

    assert result["supported"] is False
    assert result["measurements"] == []


def test_power_telemetry_reads_hwmon_units(tmp_path, monkeypatch):
    root = tmp_path / "hwmon"
    device = root / "hwmon0"
    device.mkdir(parents=True)

    write(device / "name", "test-pmic")
    write(device / "power1_input", "5250000")
    write(device / "power1_label", "input power")
    write(device / "in1_input", "5100")
    write(device / "in1_label", "input voltage")
    write(device / "curr1_input", "1030")
    write(device / "curr1_label", "input current")

    monkeypatch.setattr(power.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power, "HWMON_ROOT", root)

    result = power.collect_power_telemetry()

    by_kind = {
        item["kind"]: item
        for item in result["measurements"]
    }

    assert by_kind["power"]["value"] == 5.25
    assert by_kind["power"]["unit"] == "W"
    assert by_kind["voltage"]["value"] == 5.1
    assert by_kind["voltage"]["unit"] == "V"
    assert by_kind["current"]["value"] == 1.03
    assert by_kind["current"]["unit"] == "A"


def test_invalid_sensor_value_is_skipped(tmp_path, monkeypatch):
    root = tmp_path / "hwmon"
    device = root / "hwmon0"
    device.mkdir(parents=True)

    write(device / "name", "broken")
    write(device / "power1_input", "not-a-number")

    monkeypatch.setattr(power.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power, "HWMON_ROOT", root)

    result = power.collect_power_telemetry()

    assert result["measurements"] == []


def test_empty_hwmon_does_not_guess(tmp_path, monkeypatch):
    root = tmp_path / "hwmon"
    root.mkdir()

    monkeypatch.setattr(power.platform, "system", lambda: "Linux")
    monkeypatch.setattr(power, "HWMON_ROOT", root)

    text = power.format_power_telemetry(
        power.collect_power_telemetry()
    )

    assert "ingen uppskattning" in text.lower()


def test_formatter_lists_measured_values():
    text = power.format_power_telemetry(
        {
            "supported": True,
            "platform": "Linux",
            "measurements": [
                {
                    "kind": "power",
                    "source": "pmic",
                    "label": "input",
                    "value": 4.2,
                    "unit": "W",
                    "path": "/tmp/power1_input",
                }
            ],
        }
    )

    assert "4.200 W" in text
    assert "hwmon" in text
