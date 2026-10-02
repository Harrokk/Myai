from types import SimpleNamespace

from modules.usb import usb


def test_usb_status_windows_formats_devices(monkeypatch):
    monkeypatch.setattr(usb.platform, "system", lambda: "Windows")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="USB Device A\nUSB Device B\n",
            stderr="",
        )

    monkeypatch.setattr(usb.subprocess, "run", fake_run)

    result = usb.usb_status()

    assert "USB Device A" in result
    assert "USB Device B" in result
    assert captured["command"][0] == "powershell"
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert "[System.Text.Encoding]::UTF8" in captured["command"][-1]
    assert "::new()" not in captured["command"][-1]


def test_usb_status_linux_uses_lsusb(monkeypatch):
    monkeypatch.setattr(usb.platform, "system", lambda: "Linux")

    captured = {}

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return SimpleNamespace(
            returncode=0,
            stdout="Bus 001 Device 002: Test Device\n",
            stderr="",
        )

    monkeypatch.setattr(usb.subprocess, "run", fake_run)

    result = usb.usb_status()

    assert "Test Device" in result
    assert captured["command"] == ["lsusb"]


def test_usb_status_handles_missing_platform_tool(monkeypatch):
    monkeypatch.setattr(usb.platform, "system", lambda: "Linux")

    def missing(*args, **kwargs):
        raise FileNotFoundError

    monkeypatch.setattr(usb.subprocess, "run", missing)

    result = usb.usb_status()

    assert "hittades inte" in result
