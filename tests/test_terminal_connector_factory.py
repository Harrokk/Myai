from core.terminal_connector_factory import (
    build_terminal_connector,
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
