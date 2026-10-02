from modules.pi import bus_devices


def write(path, value):
    path.write_text(str(value), encoding="utf-8")


def test_bus_inventory_is_safe_on_non_linux(monkeypatch):
    monkeypatch.setattr(bus_devices.platform, "system", lambda: "Windows")

    result = bus_devices.collect_bus_devices()

    assert result["supported"] is False
    assert result["i2c"] == []
    assert result["spi"] == []


def test_i2c_inventory_ignores_adapter_nodes(tmp_path, monkeypatch):
    root = tmp_path / "i2c"
    root.mkdir()
    (root / "i2c-1").mkdir()
    sensor = root / "1-0048"
    sensor.mkdir()
    write(sensor / "name", "tmp102")

    monkeypatch.setattr(bus_devices.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bus_devices, "I2C_ROOT", root)
    monkeypatch.setattr(bus_devices, "SPI_ROOT", tmp_path / "missing-spi")

    result = bus_devices.collect_bus_devices()

    assert len(result["i2c"]) == 1
    assert result["i2c"][0]["id"] == "1-0048"
    assert result["i2c"][0]["address"] == "0048"
    assert result["i2c"][0]["name"] == "tmp102"


def test_spi_inventory_parses_controller_and_chip_select(tmp_path, monkeypatch):
    spi_root = tmp_path / "spi"
    spi_root.mkdir()
    device = spi_root / "spi0.1"
    device.mkdir()
    write(device / "modalias", "spi:test-device")

    monkeypatch.setattr(bus_devices.platform, "system", lambda: "Linux")
    monkeypatch.setattr(bus_devices, "I2C_ROOT", tmp_path / "missing-i2c")
    monkeypatch.setattr(bus_devices, "SPI_ROOT", spi_root)

    result = bus_devices.collect_bus_devices()

    assert len(result["spi"]) == 1
    assert result["spi"][0]["controller"] == "0"
    assert result["spi"][0]["chip_select"] == "1"
    assert result["spi"][0]["name"] == "spi:test-device"


def test_formatter_states_that_no_active_scan_was_used():
    text = bus_devices.format_bus_devices(
        {
            "supported": True,
            "platform": "Linux",
            "i2c": [
                {
                    "bus": "i2c",
                    "id": "1-0048",
                    "controller": "1",
                    "address": "0048",
                    "name": "sensor",
                    "driver": "",
                }
            ],
            "spi": [],
        }
    )

    assert "0x0048" in text
    assert "Ingen aktiv buss-skanning" in text


def test_empty_inventory_is_reported_without_guessing():
    text = bus_devices.format_bus_devices(
        {
            "supported": True,
            "platform": "Linux",
            "i2c": [],
            "spi": [],
        }
    )

    assert "inga kernel-registrerade" in text
