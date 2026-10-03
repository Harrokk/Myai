from core.terminal_connector_factory import (
    build_terminal_connector,
    build_terminal_handoff_monitor,
)
from modules.bluetooth.connector import (
    BleakGattConnector,
)


def settings(provider):
    return {
        "trusted_terminals": {
            "connector_provider": provider,
            "terminals": [],
        }
    }


def test_none_provider_returns_no_connector():
    assert build_terminal_connector(
        settings("none")
    ) is None


def test_bleak_gatt_provider_builds_connector():
    connector = build_terminal_connector(
        settings("bleak_gatt"),
        client_factory=lambda *args, **kwargs: None,
    )

    assert isinstance(
        connector,
        BleakGattConnector,
    )


def test_unknown_provider_is_rejected():
    try:
        build_terminal_connector(
            settings("magic")
        )
    except ValueError as error:
        assert "magic" in str(error)
    else:
        raise AssertionError(
            "Unknown connector should fail"
        )



def test_monitor_factory_does_not_build_connector_when_auto_execute_off():
    value = settings("bleak_gatt")
    value["trusted_terminals"]["auto_execute"] = False

    monitor = build_terminal_handoff_monitor(
        value,
        scanner=lambda timeout: [],
        client_factory=lambda *args, **kwargs: None,
    )

    assert monitor.connector is None
    assert monitor.auto_execute is False


def test_monitor_factory_wires_connector_when_auto_execute_on():
    value = settings("bleak_gatt")
    value["trusted_terminals"]["auto_execute"] = True
    value["trusted_terminals"]["require_service_uuid"] = True
    value["trusted_terminals"]["terminals"] = [
        {
            "id": "car-terminal",
            "trusted": True,
            "auto_connect": True,
            "transport": "bleak_gatt",
            "service_uuid": "1234",
        }
    ]

    monitor = build_terminal_handoff_monitor(
        value,
        scanner=lambda timeout: [],
        client_factory=lambda *args, **kwargs: None,
    )

    assert isinstance(
        monitor.connector,
        BleakGattConnector,
    )
    assert monitor.auto_execute is True
