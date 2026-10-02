import json

from core.device_registry import (
    DeviceRegistry,
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
    assert created[0]["configured"] is False
    assert created[0]["configuration"] == {}
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
    assert updated["configured"] is False
    assert updated["label"] == "Webbkamera"
    assert registry.list_records(known=False) == []
    assert registry.list_records(known=True)[0]["label"] == "Webbkamera"


def test_configuration_proposal_does_not_mutate_registry(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    proposal = registry.propose_configuration("A")
    stored = registry.get_record("A")

    assert proposal["requires_confirmation"] is True
    assert proposal["configuration"]["mode"] == "registered_only"
    assert proposal["configuration"]["auto_actions"] is False
    assert stored["known"] is False
    assert stored["configured"] is False
    assert stored["configuration"] == {}


def test_approve_configuration_persists_safe_state(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])
    proposal = registry.propose_configuration("A")

    updated = registry.approve_configuration(
        "A",
        label="Webbkamera",
        configuration=proposal["configuration"],
    )

    assert updated["known"] is True
    assert updated["configured"] is True
    assert updated["label"] == "Webbkamera"
    assert updated["configuration"]["mode"] == "registered_only"
    assert updated["configuration"]["auto_actions"] is False

    stored = registry.get_record("A")
    assert stored == updated


def test_approve_configuration_rejects_auto_actions(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A")])

    try:
        registry.approve_configuration(
            "A",
            configuration={
                "mode": "registered_only",
                "auto_actions": True,
            },
        )
    except ValueError as error:
        assert "separat framtida godkännandeflöde" in str(error)
    else:
        raise AssertionError("Automatiska åtgärder skulle ha avvisats")


def test_legacy_registry_records_get_safe_configuration_defaults(tmp_path):
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
                        "name": "Legacy",
                        "status": "OK",
                        "source": "test",
                        "known": True,
                        "label": "",
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    record = DeviceRegistry(path).get_record("A")

    assert record["configured"] is False
    assert record["configuration"] == {}


def test_format_device_records_includes_state_and_identifier(tmp_path):
    registry = DeviceRegistry(tmp_path / "devices.json")
    registry.observe_devices([make_device("A", "Camera")])

    text = format_device_records(registry.list_records())

    assert "[okänd]" in text
    assert "[ej konfigurerad]" in text
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
