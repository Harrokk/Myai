from modules.pi import interfaces


def test_collect_interfaces_is_safe_on_non_linux(monkeypatch):
    monkeypatch.setattr(interfaces.platform, "system", lambda: "Windows")

    result = interfaces.collect_pi_interfaces()

    assert result["supported"] is False
    assert result["interfaces"] == {}


def test_collect_interfaces_groups_linux_devices(monkeypatch):
    monkeypatch.setattr(interfaces.platform, "system", lambda: "Linux")

    matches = {
        "/dev/gpiochip*": ["/dev/gpiochip0"],
        "/dev/i2c-*": ["/dev/i2c-1"],
        "/dev/spidev*": ["/dev/spidev0.0", "/dev/spidev0.1"],
        "/dev/ttyAMA*": ["/dev/ttyAMA0"],
        "/dev/ttyS*": ["/dev/ttyS0"],
    }

    monkeypatch.setattr(
        interfaces.glob,
        "glob",
        lambda pattern: list(matches.get(pattern, [])),
    )

    result = interfaces.collect_pi_interfaces()

    assert result["supported"] is True
    assert result["interfaces"]["gpio"] == ["/dev/gpiochip0"]
    assert result["interfaces"]["i2c"] == ["/dev/i2c-1"]
    assert result["interfaces"]["spi"] == [
        "/dev/spidev0.0",
        "/dev/spidev0.1",
    ]
    assert result["interfaces"]["uart"] == [
        "/dev/ttyAMA0",
        "/dev/ttyS0",
    ]


def test_duplicate_interfaces_are_removed(monkeypatch):
    monkeypatch.setattr(interfaces.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        interfaces.glob,
        "glob",
        lambda pattern: ["/dev/ttyS0", "/dev/ttyS0"]
        if "ttyS" in pattern
        else [],
    )

    result = interfaces.collect_pi_interfaces()

    assert result["interfaces"]["uart"] == ["/dev/ttyS0"]


def test_format_interfaces_lists_missing_and_present():
    text = interfaces.format_pi_interfaces(
        {
            "supported": True,
            "platform": "Linux",
            "interfaces": {
                "gpio": ["/dev/gpiochip0"],
                "i2c": [],
                "spi": ["/dev/spidev0.0"],
                "uart": [],
            },
        }
    )

    assert "/dev/gpiochip0" in text
    assert "/dev/spidev0.0" in text
    assert "I2C: inget" in text
    assert "UART/seriell: inget" in text


def test_format_interfaces_explains_non_linux():
    text = interfaces.format_pi_interfaces(
        {
            "supported": False,
            "platform": "Windows",
            "interfaces": {},
        }
    )

    assert "Windows" in text
    assert "endast" in text
