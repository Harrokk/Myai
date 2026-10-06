import pytest

from core.ventuno_rpc import VentunoRPCClient


class FakeBridge:
    def __init__(self):
        self.connect_calls = []
        self.calls = []
        self.notifications = []
        self.disconnect_calls = 0

    def connect(self, timeout=5):
        self.connect_calls.append(timeout)
        return True

    def call(self, method, *args, timeout=5):
        self.calls.append(
            (method, args, timeout)
        )
        return {
            "method": method,
            "args": args,
        }

    def notify(self, method, *args):
        self.notifications.append(
            (method, args)
        )
        return True

    def disconnect(self):
        self.disconnect_calls += 1
        return True


def settings(
    enabled=True,
    rpc_enabled=True,
    write_enabled=False,
):
    return {
        "ventuno": {
            "enabled": enabled,
            "rpc_enabled": rpc_enabled,
            "rpc_write_enabled": write_enabled,
            "rpc_connect_timeout_seconds": 2,
            "rpc_call_timeout_seconds": 3,
            "rpc_allowed_read_methods": [
                "myai.read_sensor",
            ],
            "rpc_allowed_write_methods": [
                "myai.set_output",
            ],
        }
    }


def test_disabled_rpc_fails_closed():
    client = VentunoRPCClient(
        settings(enabled=False),
        bridge=FakeBridge(),
    )

    with pytest.raises(
        RuntimeError,
        match="avstängt",
    ):
        client.connect()


def test_unlisted_read_method_is_blocked_before_connect():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(),
        bridge=bridge,
    )

    with pytest.raises(
        PermissionError,
        match="allowlistad",
    ):
        client.call(
            "unknown.read"
        )

    assert bridge.connect_calls == []


def test_allowed_read_method_connects_and_calls_bridge():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(),
        bridge=bridge,
    )

    result = client.call(
        "myai.read_sensor",
        "temperature",
    )

    assert bridge.connect_calls == [
        2.0
    ]
    assert bridge.calls == [
        (
            "myai.read_sensor",
            ("temperature",),
            3.0,
        )
    ]
    assert result["method"] == (
        "myai.read_sensor"
    )


def test_write_is_blocked_by_default():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(
            write_enabled=False
        ),
        bridge=bridge,
    )

    with pytest.raises(
        PermissionError,
        match="skrivning",
    ):
        client.call(
            "myai.set_output",
            17,
            True,
            write=True,
        )

    assert bridge.calls == []


def test_allowlisted_write_can_be_enabled_explicitly():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(
            write_enabled=True
        ),
        bridge=bridge,
    )

    client.call(
        "myai.set_output",
        17,
        True,
        write=True,
        timeout=1.5,
    )
    client.notify(
        "myai.set_output",
        17,
        False,
    )

    assert bridge.calls[-1] == (
        "myai.set_output",
        (17, True),
        1.5,
    )
    assert bridge.notifications == [
        (
            "myai.set_output",
            (17, False),
        )
    ]


def test_disconnect_resets_connection_state():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(),
        bridge=bridge,
    )
    client.connect()

    assert client.disconnect() is True
    assert client.connected is False
    assert bridge.disconnect_calls == 1


def test_status_reports_policy_without_connecting():
    bridge = FakeBridge()
    client = VentunoRPCClient(
        settings(),
        bridge=bridge,
    )

    status = client.status()

    assert status["enabled"] is True
    assert status["connected"] is False
    assert status["write_enabled"] is False
    assert status[
        "allowed_read_methods"
    ] == ["myai.read_sensor"]
    assert bridge.connect_calls == []
