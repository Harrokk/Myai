from types import SimpleNamespace

from modules.bluetooth.connector import (
    BleakGattConnector,
)


def settings(
    trusted=True,
    transport="bleak_gatt",
    service_uuid="1234",
    require_service_uuid=True,
):
    return {
        "trusted_terminals": {
            "connector_timeout_seconds": 10,
            "require_service_uuid": require_service_uuid,
            "terminals": [
                {
                    "id": "car-terminal",
                    "trusted": trusted,
                    "auto_connect": True,
                    "transport": transport,
                    "service_uuid": service_uuid,
                }
            ],
        }
    }


class FakeClient:
    def __init__(
        self,
        address,
        timeout,
        service_uuids=None,
        connect_success=True,
    ):
        self.address = address
        self.timeout = timeout
        self.is_connected = False
        self.connect_success = connect_success
        self.connect_calls = 0
        self.disconnect_calls = 0
        self.services = [
            SimpleNamespace(uuid=value)
            for value in (
                service_uuids
                if service_uuids is not None
                else ["1234"]
            )
        ]

    async def connect(self):
        self.connect_calls += 1
        self.is_connected = bool(
            self.connect_success
        )
        return self.is_connected

    async def disconnect(self):
        self.disconnect_calls += 1
        self.is_connected = False
        return True


class ClientFactory:
    def __init__(
        self,
        service_uuids=None,
        connect_success=True,
    ):
        self.service_uuids = service_uuids
        self.connect_success = connect_success
        self.clients = []

    def __call__(
        self,
        address,
        timeout,
    ):
        client = FakeClient(
            address,
            timeout,
            service_uuids=self.service_uuids,
            connect_success=self.connect_success,
        )
        self.clients.append(client)
        return client


def test_connector_rejects_unknown_terminal_without_network():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )

    result = connector.connect(
        "unknown"
    )

    assert result["success"] is False
    assert factory.clients == []


def test_connector_rejects_untrusted_terminal():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(trusted=False),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is False
    assert "inte markerad som betrodd" in result["reason"]
    assert factory.clients == []


def test_connector_requires_bleak_gatt_transport():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(
            transport="classic",
        ),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is False
    assert "inte bleak_gatt" in result["reason"]


def test_connector_requires_service_uuid_by_default():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(
            service_uuid=None,
        ),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is False
    assert "service_uuid" in result["reason"]
    assert factory.clients == []


def test_connector_connects_and_verifies_expected_service():
    factory = ClientFactory(
        service_uuids=[
            "9999",
            "1234",
        ]
    )
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is True
    assert connector.is_connected(
        "car-terminal"
    ) is True
    assert len(factory.clients) == 1
    assert factory.clients[0].timeout == 10


def test_connector_disconnects_cached_client():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )
    connector.connect(
        "car-terminal"
    )

    result = connector.disconnect(
        "car-terminal"
    )

    assert result["success"] is True
    assert connector.is_connected(
        "car-terminal"
    ) is False
    assert factory.clients[0].disconnect_calls == 1


def test_connector_does_not_duplicate_active_connection():
    factory = ClientFactory()
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )

    first = connector.connect(
        "car-terminal"
    )
    second = connector.connect(
        "car-terminal"
    )

    assert first["success"] is True
    assert second["success"] is True
    assert second["already_connected"] is True
    assert len(factory.clients) == 1


def test_connector_disconnects_if_service_uuid_missing():
    factory = ClientFactory(
        service_uuids=["9999"]
    )
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is False
    assert "hittades inte" in result["reason"]
    assert factory.clients[0].disconnect_calls == 1
    assert connector.is_connected(
        "car-terminal"
    ) is False


def test_connector_reports_connect_failure():
    factory = ClientFactory(
        connect_success=False
    )
    connector = BleakGattConnector(
        settings(),
        client_factory=factory,
    )

    result = connector.connect(
        "car-terminal"
    )

    assert result["success"] is False
    assert connector.is_connected(
        "car-terminal"
    ) is False


def test_disconnect_unknown_cached_connection_is_idempotent():
    connector = BleakGattConnector(
        settings(),
        client_factory=ClientFactory(),
    )

    result = connector.disconnect(
        "car-terminal"
    )

    assert result["success"] is True
    assert result[
        "already_disconnected"
    ] is True
