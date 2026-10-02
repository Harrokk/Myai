from core.hardware_monitor import (
    HardwareMonitor,
    format_hardware_changes,
    has_hardware_changes,
)


def make_device(device_id, name, status="OK"):
    return {
        "category": "USB",
        "name": name,
        "id": device_id,
        "status": status,
        "source": "test",
    }


def test_poll_once_establishes_baseline_without_change():
    snapshots = [
        [make_device("A", "Existing")],
    ]

    monitor = HardwareMonitor(
        inventory_reader=lambda: snapshots.pop(0),
    )

    changes = monitor.poll_once()

    assert changes == {
        "added": [],
        "removed": [],
        "changed": [],
    }


def test_poll_once_detects_added_device_and_calls_callback():
    snapshots = [
        [make_device("A", "Existing")],
        [
            make_device("A", "Existing"),
            make_device("B", "New Camera"),
        ],
    ]
    events = []

    monitor = HardwareMonitor(
        inventory_reader=lambda: snapshots.pop(0),
        on_change=events.append,
    )

    monitor.poll_once()
    changes = monitor.poll_once()

    assert [item["id"] for item in changes["added"]] == ["B"]
    assert len(events) == 1


def test_poll_once_detects_removed_and_changed_devices():
    snapshots = [
        [
            make_device("A", "Old Device"),
            make_device("B", "Mouse", "OK"),
        ],
        [
            make_device("B", "Mouse", "Error"),
        ],
    ]

    monitor = HardwareMonitor(
        inventory_reader=lambda: snapshots.pop(0),
    )

    monitor.poll_once()
    changes = monitor.poll_once()

    assert [item["id"] for item in changes["removed"]] == ["A"]
    assert changes["changed"][0]["after"]["status"] == "Error"


def test_format_hardware_changes():
    changes = {
        "added": [make_device("A", "Camera")],
        "removed": [make_device("B", "Old Disk")],
        "changed": [
            {
                "before": make_device("C", "Mouse", "OK"),
                "after": make_device("C", "Mouse", "Error"),
            }
        ],
    }

    result = format_hardware_changes(changes)

    assert "+ Ny: [USB] Camera" in result
    assert "- Borttagen: [USB] Old Disk" in result
    assert "~ Ändrad: [USB] Mouse (OK -> Error)" in result
    assert has_hardware_changes(changes) is True


def test_start_reports_baseline_error_without_thread():
    errors = []

    def broken_reader():
        raise RuntimeError("boom")

    monitor = HardwareMonitor(
        inventory_reader=broken_reader,
        on_error=errors.append,
    )

    assert monitor.start() is False
    assert monitor.is_running is False
    assert str(errors[0]) == "boom"
