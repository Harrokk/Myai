import json

from core.device_registry import (
    DeviceRegistry,
    format_configuration_prompt,
    format_device_records,
)


def make_device(device_id="USB\\TEST", name="Test Device", status="OK"):
    return {
        "category": "USB",
        "name": name,
        "id": device_id,
        "status": status,
        "source": "test",
    }


def test_observe_devices_registers_new_device_as_unknown(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")

    created = registry.observe_devices([make_device()])

    assert len(created) == 1
    assert created[0]["known"] is False
    assert created[0]["configuration_status"] == "pending"
    assert registry.path.exists()

    stored = registry.list_records()
    assert len(stored) == 1
    assert stored[0]["name"] == "Test Device"


def test_observe_devices_does_not_duplicate_existing_device(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")

    registry.observe_devices([make_device()])
    created = registry.observe_devices(
        [make_device(name="Updated Device", status="Error")]
    )

    assert created == []

    stored = registry.list_records()
    assert len(stored) == 1
    assert stored[0]["name"] == "Updated Device"
    assert stored[0]["status"] == "Error"


def test_observe_changes_only_registers_added_devices(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")

    created = registry.observe_changes(
        {
            "added": [make_device("A", "Added")],
            "removed": [make_device("B", "Removed")],
            "changed": [],
        }
    )

    assert [record["key"] for record in created] == ["A"]
    assert [record["key"] for record in registry.list_records()] == ["A"]


def test_mark_known_persists_state_and_label(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    updated = registry.mark_known("A", label="Webbkamera")

    assert updated["known"] is True
    assert updated["label"] == "Webbkamera"
    assert registry.list_records(known=False) == []
    assert registry.list_records(known=True)[0]["label"] == "Webbkamera"


def test_format_device_records_includes_state_and_identifier(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    text = format_device_records(registry.list_records())

    assert "[okänd]" in text
    assert "Camera" in text
    assert "id=A" in text


def test_invalid_registry_schema_is_rejected(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(json.dumps([]), encoding="utf-8")
    registry = DeviceRegistry(path)

    try:
        registry.list_records()
    except ValueError as error:
        assert "JSON-objekt" in str(error)
    else:
        raise AssertionError("Ogiltigt register skulle ha avvisats")


def test_approve_configuration_persists_decision_and_label(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    updated = registry.approve_configuration("A", label="Webbkamera")

    assert updated["known"] is True
    assert updated["configuration_status"] == "approved"
    assert updated["label"] == "Webbkamera"
    assert registry.list_pending() == []


def test_reject_configuration_persists_decision(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    updated = registry.reject_configuration("A")

    assert updated["known"] is False
    assert updated["configuration_status"] == "rejected"
    assert registry.list_pending() == []


def test_old_registry_records_are_migrated_in_memory(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "devices": {
                    "A": {
                        "key": "A",
                        "id": "A",
                        "category": "USB",
                        "name": "Old",
                        "status": "OK",
                        "source": "test",
                        "known": False,
                        "label": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    registry = DeviceRegistry(path)
    record = registry.get_record("A")

    assert record["configuration_status"] == "pending"


def test_configuration_prompt_contains_explicit_approval_commands(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    record = registry.observe_devices([make_device("A", "Camera")])[0]

    text = format_configuration_prompt(record)

    assert "Ny okänd enhet" in text
    assert "/device approve A" in text
    assert "/device reject A" in text
