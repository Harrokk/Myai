from types import SimpleNamespace

from modules.bluetooth import bluetooth


def test_bluetooth_status_windows_uses_utf8(monkeypatch):
    monkeypatch.setattr(
        bluetooth.platform,
        "system",
        lambda: "Windows",
    )

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="Xbox Wireless Controller\nRazer Headset\n",
            stderr="",
        )

    monkeypatch.setattr(
        bluetooth.subprocess,
        "run",
        fake_run,
    )

    result = bluetooth.bluetooth_status()

    assert "Xbox Wireless Controller" in result
    assert captured["command"][0] == "powershell"
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert "[System.Text.Encoding]::UTF8" in captured["command"][-1]
    assert "-Class Bluetooth" not in captured["command"][-1]
    assert "InstanceId" in captured["command"][-1]


def test_bluetooth_status_linux_uses_bluetoothctl(monkeypatch):
    monkeypatch.setattr(
        bluetooth.platform,
        "system",
        lambda: "Linux",
    )

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        return SimpleNamespace(
            returncode=0,
            stdout="Device AA:BB:CC:DD:EE:FF Test Device\n",
            stderr="",
        )

    monkeypatch.setattr(
        bluetooth.subprocess,
        "run",
        fake_run,
    )

    result = bluetooth.bluetooth_status()

    assert "Test Device" in result
    assert captured["command"] == ["bluetoothctl", "devices"]


def test_bluetooth_status_handles_missing_tool(monkeypatch):
    monkeypatch.setattr(
        bluetooth.platform,
        "system",
        lambda: "Linux",
    )

    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(
        bluetooth.subprocess,
        "run",
        missing,
    )

    result = bluetooth.bluetooth_status()

    assert "hittades inte" in result


def test_bluetooth_status_windows_handles_no_devices(monkeypatch):
    monkeypatch.setattr(
        bluetooth.platform,
        "system",
        lambda: "Windows",
    )

    monkeypatch.setattr(
        bluetooth.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout="",
            stderr="",
        ),
    )

    result = bluetooth.bluetooth_status()

    assert result == "Inga Bluetooth-enheter hittades."
