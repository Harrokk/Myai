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


def test_compare_hardware_snapshots_detects_added_removed_and_changed():
    previous = [
        {
            "category": "USB",
            "name": "Old Device",
            "id": "A",
            "status": "OK",
            "source": "test",
        },
        {
            "category": "HIDClass",
            "name": "Mouse",
            "id": "B",
            "status": "OK",
            "source": "test",
        },
    ]

    current = [
        {
            "category": "HIDClass",
            "name": "Mouse",
            "id": "B",
            "status": "Error",
            "source": "test",
        },
        {
            "category": "USB",
            "name": "New Device",
            "id": "C",
            "status": "OK",
            "source": "test",
        },
    ]

    changes = hardware.compare_hardware_snapshots(
        previous,
        current,
    )

    assert [item["id"] for item in changes["added"]] == ["C"]
    assert [item["id"] for item in changes["removed"]] == ["A"]
    assert changes["changed"][0]["after"]["id"] == "B"


def test_hardware_changes_creates_baseline(tmp_path, monkeypatch):
    snapshot = tmp_path / "hardware_snapshot.json"

    devices = [
        {
            "category": "USB",
            "name": "Device",
            "id": "A",
            "status": "OK",
            "source": "test",
        }
    ]

    monkeypatch.setattr(
        hardware,
        "get_hardware_inventory",
        lambda: devices,
    )

    result = hardware.hardware_changes(snapshot)

    assert "baslinje skapad" in result
    assert snapshot.exists()


def test_hardware_changes_reports_new_device(tmp_path, monkeypatch):
    snapshot = tmp_path / "hardware_snapshot.json"

    hardware.save_hardware_snapshot(
        [
            {
                "category": "USB",
                "name": "Existing",
                "id": "A",
                "status": "OK",
                "source": "test",
            }
        ],
        snapshot,
    )

    monkeypatch.setattr(
        hardware,
        "get_hardware_inventory",
        lambda: [
            {
                "category": "USB",
                "name": "Existing",
                "id": "A",
                "status": "OK",
                "source": "test",
            },
            {
                "category": "USB",
                "name": "New Camera",
                "id": "B",
                "status": "OK",
                "source": "test",
            },
        ],
    )

    result = hardware.hardware_changes(snapshot)

    assert "Ny: [USB] New Camera" in result


def test_hardware_changes_reports_no_change(tmp_path, monkeypatch):
    snapshot = tmp_path / "hardware_snapshot.json"

    devices = [
        {
            "category": "USB",
            "name": "Existing",
            "id": "A",
            "status": "OK",
            "source": "test",
        }
    ]

    hardware.save_hardware_snapshot(
        devices,
        snapshot,
    )

    monkeypatch.setattr(
        hardware,
        "get_hardware_inventory",
        lambda: devices,
    )

    result = hardware.hardware_changes(snapshot)

    assert result == "Ingen förändring i hårdvaran upptäcktes."
