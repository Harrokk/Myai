import hashlib
import hmac
import json
from types import SimpleNamespace

from core.terminal_session import (
    TerminalSessionAuthenticator,
    terminal_auth_digest,
)


def settings(**terminal_overrides):
    terminal = {
        "id": "car-terminal",
        "trusted": True,
        "auto_connect": True,
        "transport": "bleak_gatt",
        "protocol": "myai-terminal-v1",
        "auth_key_env": "MYAI_CAR_KEY",
        "command_characteristic_uuid": "abcd",
        "response_characteristic_uuid": "dcba",
    }
    terminal.update(
        terminal_overrides
    )
    return {
        "trusted_terminals": {
            "terminals": [
                terminal
            ],
        }
    }


class FakeClient:
    def __init__(
        self,
        device_id="car-terminal",
        secret="secret",
        protocol="myai-terminal-v1",
        response_overrides=None,
        characteristics=None,
    ):
        self.device_id = device_id
        self.secret = secret
        self.protocol = protocol
        self.response_overrides = (
            response_overrides or {}
        )
        self.is_connected = True
        char_values = (
            characteristics
            if characteristics is not None
            else [
                "0000abcd-0000-1000-8000-00805f9b34fb",
                "0000dcba-0000-1000-8000-00805f9b34fb",
            ]
        )
        self.services = [
            SimpleNamespace(
                characteristics=[
                    SimpleNamespace(
                        uuid=value
                    )
                    for value in char_values
                ]
            )
        ]
        self.writes = []

    async def write_gatt_char(
        self,
        uuid,
        payload,
        response=True,
    ):
        self.writes.append(
            (
                uuid,
                bytes(payload),
                response,
            )
        )

    async def read_gatt_char(
        self,
        uuid,
    ):
        challenge = json.loads(
            self.writes[-1][
                1
            ].decode("utf-8")
        )
        nonce = challenge[
            "nonce"
        ]
        digest = terminal_auth_digest(
            self.secret,
            self.protocol,
            self.device_id,
            nonce,
        )
        response = {
            "type": "auth_response",
            "protocol": self.protocol,
            "terminal_id": self.device_id,
            "nonce": nonce,
            "hmac_sha256": digest,
        }
        response.update(
            self.response_overrides
        )
        return json.dumps(
            response
        ).encode("utf-8")


class FakeConnector:
    def __init__(
        self,
        client=None,
        connected=True,
    ):
        self.client = (
            client
            if client is not None
            else FakeClient()
        )
        self.connected = connected

    def get_client(
        self,
        device_id,
    ):
        if (
            self.connected
            and device_id
            == "car-terminal"
        ):
            return self.client
        return None

    def is_connected(
        self,
        device_id,
    ):
        return bool(
            self.connected
            and device_id
            == "car-terminal"
            and self.client.is_connected
        )


def authenticator(
    client=None,
    env=None,
    **terminal_overrides,
):
    return TerminalSessionAuthenticator(
        settings(
            **terminal_overrides
        ),
        FakeConnector(
            client=client
        ),
        env=(
            {
                "MYAI_CAR_KEY": "secret"
            }
            if env is None
            else env
        ),
        nonce_factory=(
            lambda: "fixed-nonce"
        ),
    )


def test_digest_is_deterministic_hmac_sha256():
    expected = hmac.new(
        b"secret",
        (
            "myai-terminal-v1|"
            "car-terminal|"
            "nonce"
        ).encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    assert terminal_auth_digest(
        "secret",
        "myai-terminal-v1",
        "car-terminal",
        "nonce",
    ) == expected


def test_authenticate_valid_terminal():
    auth = authenticator()

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is True
    assert auth.is_authenticated(
        "car-terminal"
    ) is True
    assert auth.status()[
        "authenticated_ids"
    ] == ["car-terminal"]


def test_secret_is_never_sent_in_challenge():
    client = FakeClient()
    auth = authenticator(
        client=client
    )

    auth.authenticate(
        "car-terminal"
    )

    payload = client.writes[
        0
    ][1].decode("utf-8")
    assert "secret" not in payload
    assert "fixed-nonce" in payload


def test_missing_environment_secret_fails_closed():
    auth = authenticator(
        env={}
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "MYAI_CAR_KEY" in result[
        "reason"
    ]


def test_wrong_hmac_fails():
    client = FakeClient(
        secret="wrong"
    )
    auth = authenticator(
        client=client
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "HMAC" in result[
        "reason"
    ]


def test_wrong_nonce_fails():
    client = FakeClient(
        response_overrides={
            "nonce": "old-nonce"
        }
    )
    auth = authenticator(
        client=client
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "nonce" in result[
        "reason"
    ]


def test_wrong_terminal_id_fails():
    client = FakeClient(
        response_overrides={
            "terminal_id": "other"
        }
    )
    auth = authenticator(
        client=client
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "terminal_id" in result[
        "reason"
    ]


def test_wrong_protocol_response_fails():
    client = FakeClient(
        response_overrides={
            "protocol": "myai-terminal-v2"
        }
    )
    auth = authenticator(
        client=client
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "protocol" in result[
        "reason"
    ]


def test_unsupported_configured_protocol_fails_before_io():
    client = FakeClient()
    auth = authenticator(
        client=client,
        protocol="myai-terminal-v2",
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert client.writes == []


def test_missing_required_characteristic_fails():
    client = FakeClient(
        characteristics=[
            "0000abcd-0000-1000-8000-00805f9b34fb"
        ]
    )
    auth = authenticator(
        client=client
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "characteristics" in result[
        "reason"
    ]


def test_requires_active_connector_owned_client():
    auth = TerminalSessionAuthenticator(
        settings(),
        FakeConnector(
            connected=False
        ),
        env={
            "MYAI_CAR_KEY": "secret"
        },
        nonce_factory=(
            lambda: "nonce"
        ),
    )

    result = auth.authenticate(
        "car-terminal"
    )

    assert result["success"] is False
    assert "Ingen aktiv" in result[
        "reason"
    ]


def test_clear_removes_authenticated_state():
    auth = authenticator()
    auth.authenticate(
        "car-terminal"
    )

    assert auth.clear(
        "car-terminal"
    ) is True
    assert auth.is_authenticated(
        "car-terminal"
    ) is False
