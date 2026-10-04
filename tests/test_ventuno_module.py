from modules.ventuno.ventuno import (
    read_ventuno_mcu_status,
)


class FakeClient:
    def __init__(
        self,
        enabled=True,
        fail_on=None,
    ):
        self.enabled = enabled
        self.fail_on = fail_on
        self.calls = []
        self.disconnect_calls = 0

    def call(self, method):
        self.calls.append(method)

        if method == self.fail_on:
            raise RuntimeError(
                "rpc-fel"
            )

        return {
            "myai_ping": "pong",
            "myai_uptime_ms": 1234,
            "myai_mcu_status": (
                "ventuno-mcu-ready"
            ),
        }[method]

    def disconnect(self):
        self.disconnect_calls += 1
        return True


def test_mcu_status_is_read_only_and_uses_fixed_methods():
    client = FakeClient()

    result = read_ventuno_mcu_status(
        settings={},
        client=client,
    )

    assert client.calls == [
        "myai_ping",
        "myai_uptime_ms",
        "myai_mcu_status",
    ]
    assert "Ping: pong" in result
    assert "Uptime: 1234 ms" in result
    assert (
        "Status: ventuno-mcu-ready"
        in result
    )
    assert client.disconnect_calls == 1


def test_mcu_status_does_not_connect_when_rpc_disabled():
    client = FakeClient(
        enabled=False
    )

    result = read_ventuno_mcu_status(
        settings={},
        client=client,
    )

    assert "avstängt" in result
    assert client.calls == []
    assert client.disconnect_calls == 0


def test_mcu_status_disconnects_if_read_fails():
    client = FakeClient(
        fail_on="myai_uptime_ms"
    )

    try:
        read_ventuno_mcu_status(
            settings={},
            client=client,
        )
    except RuntimeError as error:
        assert "rpc-fel" in str(error)
    else:
        raise AssertionError(
            "RPC-felet skulle ha propagerats."
        )

    assert client.disconnect_calls == 1
