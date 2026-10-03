import asyncio

from core.terminal_policy import find_terminal_config


def _normalize_uuid(value):
    text = str(value or "").strip().lower()

    if len(text) == 4:
        try:
            int(text, 16)
        except ValueError:
            return text

        return (
            f"0000{text}-0000-1000-8000-00805f9b34fb"
        )

    if len(text) == 8:
        try:
            int(text, 16)
        except ValueError:
            return text

        return (
            f"{text}-0000-1000-8000-00805f9b34fb"
        )

    return text


def _service_uuids(client):
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

        if isinstance(values, dict):
            iterable = values.values()
        else:
            iterable = values
    else:
        iterable = services

    try:
        return {
            _normalize_uuid(
                getattr(
                    service,
                    "uuid",
                    service,
                )
            )
            for service in iterable
            if _normalize_uuid(
                getattr(
                    service,
                    "uuid",
                    service,
                )
            )
        }
    except TypeError:
        return set()


class BleakGattConnector:
    def __init__(
        self,
        settings,
        client_factory=None,
    ):
        self.settings = settings
        self.config = settings.get(
            "trusted_terminals",
            {},
        )
        self.timeout_seconds = max(
            1.0,
            float(
                self.config.get(
                    "connector_timeout_seconds",
                    10.0,
                )
            ),
        )
        self.require_service_uuid = bool(
            self.config.get(
                "require_service_uuid",
                True,
            )
        )
        self._client_factory = client_factory
        self._clients = {}

    def _factory(self):
        if self._client_factory is not None:
            return self._client_factory

        try:
            from bleak import BleakClient
        except ImportError as error:
            raise RuntimeError(
                "BLE GATT-anslutning kräver bleak."
            ) from error

        return BleakClient

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

        transport = (
            terminal.get("transport")
            or ""
        ).strip().lower()

        if transport != "bleak_gatt":
            return None, (
                "Terminalens transport är inte bleak_gatt."
            )

        if (
            self.require_service_uuid
            and not terminal.get(
                "service_uuid"
            )
        ):
            return None, (
                "Terminalen saknar obligatoriskt service_uuid."
            )

        return terminal, None

    def _run(self, async_function, *args):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(
                async_function(*args)
            )

        raise RuntimeError(
            "BLE GATT-connectorn kan inte köras synkront "
            "inuti en redan aktiv asyncio-loop."
        )

    async def _connect_async(
        self,
        device_id,
        terminal,
    ):
        existing = self._clients.get(
            device_id
        )

        if (
            existing is not None
            and bool(
                getattr(
                    existing,
                    "is_connected",
                    False,
                )
            )
        ):
            return {
                "success": True,
                "already_connected": True,
                "device_id": device_id,
            }

        factory = self._factory()
        client = factory(
            device_id,
            timeout=self.timeout_seconds,
        )

        try:
            result = await client.connect()
            connected = bool(
                getattr(
                    client,
                    "is_connected",
                    result,
                )
            )

            if not connected:
                return {
                    "success": False,
                    "device_id": device_id,
                    "reason": (
                        "Bleak rapporterade ingen aktiv GATT-anslutning."
                    ),
                }

            expected_uuid = _normalize_uuid(
                terminal.get(
                    "service_uuid"
                )
            )

            if expected_uuid:
                available = _service_uuids(
                    client
                )

                if expected_uuid not in available:
                    try:
                        await client.disconnect()
                    finally:
                        return {
                            "success": False,
                            "device_id": device_id,
                            "reason": (
                                "Förväntat GATT service_uuid "
                                f"{expected_uuid} hittades inte."
                            ),
                            "available_service_uuids": sorted(
                                available
                            ),
                        }

            self._clients[
                device_id
            ] = client
            return {
                "success": True,
                "already_connected": False,
                "device_id": device_id,
                "service_uuid": (
                    expected_uuid
                    or None
                ),
            }
        except Exception:
            try:
                if bool(
                    getattr(
                        client,
                        "is_connected",
                        False,
                    )
                ):
                    await client.disconnect()
            finally:
                self._clients.pop(
                    device_id,
                    None,
                )
            raise

    def connect(self, device_id):
        terminal, error = self._terminal(
            device_id
        )

        if error:
            return {
                "success": False,
                "device_id": device_id,
                "reason": error,
            }

        return self._run(
            self._connect_async,
            device_id,
            terminal,
        )

    async def _disconnect_async(
        self,
        device_id,
    ):
        client = self._clients.get(
            device_id
        )

        if client is None:
            return {
                "success": True,
                "already_disconnected": True,
                "device_id": device_id,
            }

        try:
            await client.disconnect()
            connected = bool(
                getattr(
                    client,
                    "is_connected",
                    False,
                )
            )

            return {
                "success": not connected,
                "already_disconnected": False,
                "device_id": device_id,
                "reason": (
                    None
                    if not connected
                    else "Client rapporterar fortfarande ansluten."
                ),
            }
        finally:
            if not bool(
                getattr(
                    client,
                    "is_connected",
                    False,
                )
            ):
                self._clients.pop(
                    device_id,
                    None,
                )

    def disconnect(self, device_id):
        return self._run(
            self._disconnect_async,
            device_id,
        )

    def is_connected(self, device_id):
        client = self._clients.get(
            device_id
        )
        return bool(
            client is not None
            and getattr(
                client,
                "is_connected",
                False,
            )
        )

    def status(self):
        return {
            "provider": "bleak_gatt",
            "connected_ids": sorted(
                device_id
                for device_id in self._clients
                if self.is_connected(
                    device_id
                )
            ),
            "require_service_uuid": self.require_service_uuid,
            "timeout_seconds": self.timeout_seconds,
        }
