from pathlib import Path
from types import SimpleNamespace

from modules.ventuno import platform as ventuno_platform


def test_interfaces_are_read_only_linux_inventory(
    monkeypatch,
):
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        ventuno_platform.glob,
        "glob",
        lambda pattern: {
            "/dev/gpiochip*": [
                "/dev/gpiochip0",
            ],
            "/dev/i2c-*": [
                "/dev/i2c-0",
            ],
            "/dev/spidev*": [],
            "/dev/ttyHS*": [
                "/dev/ttyHS0",
            ],
            "/dev/ttyAMA*": [],
            "/dev/ttyS*": [],
        }.get(
            pattern,
            [],
        ),
    )

    result = (
        ventuno_platform
        .collect_ventuno_interfaces()
    )

    assert result[
        "supported"
    ] is True
    assert result[
        "interfaces"
    ][
        "gpio"
    ] == [
        "/dev/gpiochip0"
    ]
    assert result[
        "interfaces"
    ][
        "uart"
    ] == [
        "/dev/ttyHS0"
    ]


def test_interfaces_are_unsupported_off_linux(
    monkeypatch,
):
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Windows",
    )

    result = (
        ventuno_platform
        .collect_ventuno_interfaces()
    )

    assert result[
        "supported"
    ] is False


def test_bus_inventory_reads_only_kernel_registered_devices(
    tmp_path,
    monkeypatch,
):
    i2c_root = (
        tmp_path
        / "i2c"
    )
    spi_root = (
        tmp_path
        / "spi"
    )
    i2c_root.mkdir()
    spi_root.mkdir()

    i2c_device = (
        i2c_root
        / "1-0040"
    )
    i2c_device.mkdir()
    (
        i2c_device
        / "name"
    ).write_text(
        "sensor",
        encoding="utf-8",
    )
    (
        i2c_root
        / "i2c-1"
    ).mkdir()

    spi_device = (
        spi_root
        / "spi0.1"
    )
    spi_device.mkdir()
    (
        spi_device
        / "modalias"
    ).write_text(
        "spi:test",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ventuno_platform,
        "I2C_ROOT",
        i2c_root,
    )
    monkeypatch.setattr(
        ventuno_platform,
        "SPI_ROOT",
        spi_root,
    )
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Linux",
    )

    result = (
        ventuno_platform
        .collect_ventuno_bus_devices()
    )

    assert result[
        "i2c"
    ][
        0
    ][
        "address"
    ] == "0040"
    assert result[
        "i2c"
    ][
        0
    ][
        "name"
    ] == "sensor"
    assert result[
        "spi"
    ][
        0
    ][
        "chip_select"
    ] == "1"


def test_power_telemetry_uses_linux_hwmon_without_guessing(
    tmp_path,
    monkeypatch,
):
    root = (
        tmp_path
        / "hwmon"
    )
    device = (
        root
        / "hwmon0"
    )
    device.mkdir(
        parents=True,
    )
    (
        device
        / "name"
    ).write_text(
        "pmic",
        encoding="utf-8",
    )
    (
        device
        / "power1_input"
    ).write_text(
        "2500000",
        encoding="utf-8",
    )
    (
        device
        / "power1_label"
    ).write_text(
        "board",
        encoding="utf-8",
    )

    monkeypatch.setattr(
        ventuno_platform,
        "HWMON_ROOT",
        root,
    )
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Linux",
    )

    result = (
        ventuno_platform
        .collect_ventuno_power_telemetry()
    )

    assert result[
        "measurements"
    ][
        0
    ][
        "value"
    ] == 2.5
    assert result[
        "measurements"
    ][
        0
    ][
        "unit"
    ] == "W"


def test_network_status_uses_psutil_read_only(
    monkeypatch,
):
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        ventuno_platform.psutil,
        "net_if_stats",
        lambda: {
            "eth0": SimpleNamespace(
                isup=True,
                speed=2500,
            )
        },
    )
    monkeypatch.setattr(
        ventuno_platform.psutil,
        "net_if_addrs",
        lambda: {
            "eth0": [
                SimpleNamespace(
                    family=ventuno_platform.socket.AF_INET,
                    address="192.0.2.10",
                )
            ]
        },
    )

    result = (
        ventuno_platform
        .collect_ventuno_network_status()
    )

    assert result[
        "interfaces"
    ][
        0
    ][
        "name"
    ] == "eth0"
    assert result[
        "interfaces"
    ][
        0
    ][
        "speed_mbps"
    ] == 2500


def test_service_status_handles_missing_systemctl(
    monkeypatch,
):
    monkeypatch.setattr(
        ventuno_platform.platform,
        "system",
        lambda: "Linux",
    )
    monkeypatch.setattr(
        ventuno_platform.shutil,
        "which",
        lambda name: None,
    )

    result = (
        ventuno_platform
        .collect_ventuno_services_status()
    )

    assert result[
        "available"
    ] is False
    assert result[
        "reason"
    ] == "systemctl saknas"


def test_io_safety_never_invents_pi_pinout():
    text = (
        ventuno_platform
        .ventuno_io_safety()
    )

    assert "VENTUNO" in text
    assert "Arduino Router/RPC" in text
    assert "GPIO17" not in text
    assert "GPIO2/SDA" not in text
    assert "Raspberry Pi" not in text


def test_ventuno_platform_tool_names_have_no_pi_prefix():
    names = set(
        ventuno_platform.TOOLS
    )

    assert names == {
        "ventuno_interfaces_status",
        "ventuno_bus_devices_status",
        "ventuno_power_status",
        "ventuno_network_status",
        "ventuno_process_status",
        "ventuno_services_status",
        "ventuno_system_logs",
        "ventuno_io_safety",
    }
    assert not any(
        name.startswith(
            "pi_"
        )
        for name in names
    )
