class VentunoRPCClient:
    """Guarded wrapper around Arduino Router Bridge for VENTUNO Q."""

    def __init__(
        self,
        settings,
        bridge=None,
        bridge_factory=None,
    ):
        self.settings = settings
        self.config = settings.get(
            "ventuno",
            {},
        )
        self.bridge = bridge
        self.bridge_factory = bridge_factory
        self.connected = False

    @property
    def enabled(self):
        return bool(
            self.config.get(
                "enabled",
                False,
            )
            and self.config.get(
                "rpc_enabled",
                False,
            )
        )

    @property
    def write_enabled(self):
        return bool(
            self.config.get(
                "rpc_write_enabled",
                False,
            )
        )

    def _allowed_methods(self, write=False):
        key = (
            "rpc_allowed_write_methods"
            if write
            else "rpc_allowed_read_methods"
        )

        return {
            str(value).strip()
            for value in self.config.get(
                key,
                [],
            )
            if str(value).strip()
        }

    def _validate_method(self, method, write=False):
        name = str(method or "").strip()

        if not name:
            raise ValueError(
                "RPC-metod måste anges."
            )

        if not self.enabled:
            raise RuntimeError(
                "VENTUNO RPC är avstängt i konfigurationen."
            )

        if write and not self.write_enabled:
            raise PermissionError(
                "VENTUNO RPC-skrivning är avstängd."
            )

        allowed = self._allowed_methods(
            write=write
        )

        if name not in allowed:
            mode = (
                "skrivmetod"
                if write
                else "läsmetod"
            )
            raise PermissionError(
                f"RPC-{mode} är inte allowlistad: {name}"
            )

        return name

    def _build_bridge(self):
        if self.bridge is not None:
            return self.bridge

        if self.bridge_factory is not None:
            self.bridge = (
                self.bridge_factory()
            )
            return self.bridge

        try:
            from arduino.router_bridge import Bridge
        except ImportError as error:
            raise RuntimeError(
                "VENTUNO RPC kräver arduino-router-bridge. "
                "Installera requirements-ventuno.txt på VENTUNO Q."
            ) from error

        self.bridge = Bridge()
        return self.bridge

    def connect(self):
        if not self.enabled:
            raise RuntimeError(
                "VENTUNO RPC är avstängt i konfigurationen."
            )

        if self.connected:
            return False

        bridge = self._build_bridge()
        timeout = float(
            self.config.get(
                "rpc_connect_timeout_seconds",
                5.0,
            )
        )

        result = bridge.connect(
            timeout=timeout
        )

        if result is False:
            raise ConnectionError(
                "Kunde inte ansluta till Arduino Router."
            )

        self.connected = True
        return True

    def _ensure_connected(self):
        if not self.connected:
            self.connect()

        return self.bridge

    def call(
        self,
        method,
        *args,
        write=False,
        timeout=None,
    ):
        name = self._validate_method(
            method,
            write=write,
        )
        bridge = self._ensure_connected()
        value = (
            float(timeout)
            if timeout is not None
            else float(
                self.config.get(
                    "rpc_call_timeout_seconds",
                    5.0,
                )
            )
        )

        return bridge.call(
            name,
            *args,
            timeout=value,
        )

    def notify(
        self,
        method,
        *args,
    ):
        name = self._validate_method(
            method,
            write=True,
        )
        bridge = self._ensure_connected()

        return bridge.notify(
            name,
            *args,
        )

    def disconnect(self):
        bridge = self.bridge

        if bridge is None:
            self.connected = False
            return False

        changed = self.connected

        try:
            bridge.disconnect()
        finally:
            self.connected = False

        return changed

    def status(self):
        return {
            "enabled": self.enabled,
            "connected": self.connected,
            "write_enabled": self.write_enabled,
            "allowed_read_methods": sorted(
                self._allowed_methods(
                    write=False
                )
            ),
            "allowed_write_methods": sorted(
                self._allowed_methods(
                    write=True
                )
            ),
            "provider": (
                type(self.bridge).__name__
                if self.bridge is not None
                else "arduino-router-bridge"
            ),
        }
