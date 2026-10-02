from types import SimpleNamespace

from modules.hardware import hardware


def test_windows_inventory_normalizes_devices(monkeypatch):
    monkeypatch.setattr(
        hardware.platform,
        "system",
        lambda: "Windows",
    )

    payload = (
        '[{"Class":"USB","FriendlyName":"USB Test Device",'
        '"InstanceId":"USB\\\\TEST","Status":"OK"},'
        '{"Class":"HIDClass","FriendlyName":"Test Mouse",'
        '"InstanceId":"HID\\\\TEST","Status":"OK"}]'
    )

    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=payload,
            stderr="",
        ),
    )

    devices = hardware.get_hardware_inventory()

    assert len(devices) == 2
    assert devices[0]["category"] == "USB"
    assert devices[0]["name"] == "USB Test Device"
    assert devices[0]["source"] == "windows-pnp"


def test_windows_inventory_handles_single_json_object(monkeypatch):
    monkeypatch.setattr(
        hardware.platform,
        "system",
        lambda: "Windows",
    )

    payload = (
        '{"Class":"Bluetooth","FriendlyName":"BT Adapter",'
        '"InstanceId":"BTH\\\\TEST","Status":"OK"}'
    )

    monkeypatch.setattr(
        hardware.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0,
            stdout=payload,
            stderr="",
        ),
    )

    devices = hardware.get_hardware_inventory()

    assert len(devices) == 1
    assert devices[0]["name"] == "BT Adapter"


def test_hardware_inventory_formats_grouped_output(monkeypatch):
    monkeypatch.setattr(
        hardware,
        "get_hardware_inventory",
        lambda: [
            {
                "category": "USB",
                "name": "USB Device",
                "id": "USB-1",
                "status": "OK",
                "source": "test",
            },
            {
                "category": "Bluetooth",
                "name": "BT Device",
                "id": "BT-1",
                "status": "",
                "source": "test",
            },
        ],
    )

    result = hardware.hardware_inventory()

    assert "Identifierade hårdvaruenheter: 2" in result
    assert "USB Device [OK]" in result
    assert "BT Device" in result


def test_hardware_inventory_handles_empty_result(monkeypatch):
    monkeypatch.setattr(
        hardware,
        "get_hardware_inventory",
        lambda: [],
    )

    assert hardware.hardware_inventory() == (
        "Ingen hårdvara kunde identifieras."
    )
