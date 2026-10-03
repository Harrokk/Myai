import asyncio
import hashlib
import hmac
import json
import os
import secrets

from core.terminal_policy import find_terminal_config
from modules.bluetooth.connector import _normalize_uuid


DEFAULT_PROTOCOL = "myai-terminal-v1"
MAX_AUTH_RESPONSE_BYTES = 4096


def _characteristic_uuids(client):
    services = getattr(
        client,
        "services",
        None,
    )

    if services is None:
        return set()

    if hasattr(services, "services"):
        values = getattr(
            services,
            "services",
            {},
        )
        service_iterable = (
            values.values()
            if isinstance(values, dict)
            else values
        )
    else:
        service_iterable = services

    result = set()

    try:
        for service in service_iterable:
            characteristics = getattr(
                service,
                "characteristics",
                [],
            )

            for characteristic in characteristics:
                value = _normalize_uuid(
                    getattr(
                        characteristic,
                        "uuid",
                        characteristic,
                    )
                )

                if value:
                    result.add(value)
    except TypeError:
        return set()

    return result


def terminal_auth_digest(
    secret,
    protocol,
    device_id,
    nonce,
):
    if isinstance(secret, str):
        secret = secret.encode(
            "utf-8"
        )

    message = (
        f"{protocol}|{device_id}|{nonce}"
    ).encode("utf-8")
    return hmac.new(
        secret,
        message,
        hashlib.sha256,
    ).hexdigest()


class TerminalSessionAuthenticator:
    def __init__(
        self,
        settings,
        connector,
        env=None,
        nonce_factory=None,
    ):
        self.settings = settings
        self.config = settings.get(
            "trusted_terminals",
            {},
        )
        self.connector = connector
        self.env = (
            os.environ
            if env is None
            else env
        )
        self.nonce_factory = (
            nonce_factory
            or (
                lambda: secrets.token_hex(
                    16
                )
            )
        )
        self._authenticated = {}

    def _run(
        self,
        async_function,
        *args,
    ):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                async_function(*args)
            )

        raise RuntimeError(
            "Terminalsessionen kan inte köras synkront "
            "inuti en redan aktiv asyncio-loop."
        )

    def _terminal(self, device_id):
        terminal = find_terminal_config(
            self.settings,
            device_id,
        )

        if terminal is None:
            return None, (
                "Enheten finns inte i trusted_terminals."
            )

        if not terminal.get(
            "trusted",
            False,
        ):
            return None, (
                "Terminalen är inte markerad som betrodd."
            )

        if (
            terminal.get(
                "transport",
                "",
            ).strip().lower()
            != "bleak_gatt"
        ):
            return None, (
                "Terminalsessionen kräver transport=bleak_gatt."
            )

        protocol = (
            terminal.get(
                "protocol",
                DEFAULT_PROTOCOL,
            )
            or DEFAULT_PROTOCOL
        ).strip()

        if protocol != DEFAULT_PROTOCOL:
            return None, (
                "Terminalens protokollversion stöds inte: "
                f"{protocol}"
            )

        auth_env = (
            terminal.get(
                "auth_key_env"
            )
            or ""
        ).strip()

        if not auth_env:
            return None, (
                "Terminalen saknar auth_key_env."
            )

        command_uuid = _normalize_uuid(
            terminal.get(
                "command_characteristic_uuid"
            )
        )
        response_uuid = _normalize_uuid(
            terminal.get(
                "response_characteristic_uuid"
            )
        )

        if not command_uuid:
            return None, (
                "Terminalen saknar command_characteristic_uuid."
            )

        if not response_uuid:
            return None, (
                "Terminalen saknar response_characteristic_uuid."
            )

        return {
            **terminal,
            "protocol": protocol,
            "auth_key_env": auth_env,
            "command_characteristic_uuid": command_uuid,
            "response_characteristic_uuid": response_uuid,
        }, None

    def is_authenticated(
        self,
        device_id,
    ):
        if not self.connector.is_connected(
            device_id
        ):
            self._authenticated.pop(
                device_id,
                None,
            )
            return False

        return device_id in self._authenticated

    def clear(
        self,
        device_id,
    ):
        return (
            self._authenticated.pop(
                device_id,
                None,
            )
            is not None
        )

    async def _authenticate_async(
        self,
        device_id,
        terminal,
        client,
        secret,
    ):
        available = _characteristic_uuids(
            client
        )

        required = {
            terminal[
                "command_characteristic_uuid"
            ],
            terminal[
                "response_characteristic_uuid"
            ],
        }
        missing = sorted(
            required - available
        )

        if missing:
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Terminalen saknar nödvändiga GATT-characteristics."
                ),
                "missing_characteristic_uuids": missing,
            }

        nonce = str(
            self.nonce_factory()
        ).strip()

        if not nonce:
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Kunde inte skapa en autentiserings-challenge."
                ),
            }

        challenge = {
            "type": "auth_challenge",
            "protocol": terminal[
                "protocol"
            ],
            "terminal_id": device_id,
            "nonce": nonce,
        }
        payload = json.dumps(
            challenge,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")

        await client.write_gatt_char(
            terminal[
                "command_characteristic_uuid"
            ],
            payload,
            response=True,
        )

        raw = await client.read_gatt_char(
            terminal[
                "response_characteristic_uuid"
            ]
        )
        raw = bytes(raw)

        if len(raw) > MAX_AUTH_RESPONSE_BYTES:
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Terminalens autentiseringssvar är för stort."
                ),
            }

        try:
            response = json.loads(
                raw.decode("utf-8")
            )
        except (
            UnicodeDecodeError,
            json.JSONDecodeError,
        ):
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Terminalens autentiseringssvar är inte giltig JSON."
                ),
            }

        if not isinstance(
            response,
            dict,
        ):
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Terminalens autentiseringssvar måste vara ett objekt."
                ),
            }

        expected = {
            "type": "auth_response",
            "protocol": terminal[
                "protocol"
            ],
            "terminal_id": device_id,
            "nonce": nonce,
        }

        for key, value in expected.items():
            if response.get(key) != value:
                return {
                    "success": False,
                    "device_id": device_id,
                    "reason": (
                        f"Terminalens auth-fält {key} matchar inte challenge."
                    ),
                }

        received_digest = str(
            response.get(
                "hmac_sha256",
                "",
            )
        ).strip().lower()
        expected_digest = terminal_auth_digest(
            secret,
            terminal[
                "protocol"
            ],
            device_id,
            nonce,
        )

        if not hmac.compare_digest(
            received_digest,
            expected_digest,
        ):
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Terminalens HMAC-autentisering misslyckades."
                ),
            }

        self._authenticated[
            device_id
        ] = {
            "protocol": terminal[
                "protocol"
            ],
            "nonce": nonce,
        }

        return {
            "success": True,
            "device_id": device_id,
            "protocol": terminal[
                "protocol"
            ],
        }

    def authenticate(
        self,
        device_id,
    ):
        terminal, error = self._terminal(
            device_id
        )

        if error:
            return {
                "success": False,
                "device_id": device_id,
                "reason": error,
            }

        client = self.connector.get_client(
            device_id
        )

        if client is None:
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Ingen aktiv connector-ägd GATT-anslutning finns."
                ),
            }

        secret = self.env.get(
            terminal[
                "auth_key_env"
            ]
        )

        if not secret:
            return {
                "success": False,
                "device_id": device_id,
                "reason": (
                    "Autentiseringsnyckeln saknas i miljövariabeln "
                    f"{terminal['auth_key_env']}."
                ),
            }

        result = self._run(
            self._authenticate_async,
            device_id,
            terminal,
            client,
            secret,
        )

        if not result.get(
            "success"
        ):
            self._authenticated.pop(
                device_id,
                None,
            )

        return result

    def status(self):
        return {
            "protocol": DEFAULT_PROTOCOL,
            "authenticated_ids": sorted(
                device_id
                for device_id in self._authenticated
                if self.is_authenticated(
                    device_id
                )
            ),
        }
