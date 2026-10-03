from core.terminal_handoff import TerminalHandoffMonitor
from modules.bluetooth.connector import BleakGattConnector


def build_terminal_connector(
    settings,
    client_factory=None,
):
    config = settings.get(
        "trusted_terminals",
        {},
    )
    provider = (
        config.get(
            "connector_provider",
            "none",
        )
        or "none"
    ).strip().lower()

    if provider in {
        "none",
        "disabled",
        "off",
    }:
        return None

    if provider == "bleak_gatt":
        return BleakGattConnector(
            settings,
            client_factory=client_factory,
        )

    raise ValueError(
        f"Okänd terminal-connector: {provider}"
    )



def build_terminal_handoff_monitor(
    settings,
    scanner=None,
    on_event=None,
    on_error=None,
    client_factory=None,
):
    config = settings.get(
        "trusted_terminals",
        {},
    )
    connector = None

    if config.get(
        "auto_execute",
        False,
    ):
        connector = build_terminal_connector(
            settings,
            client_factory=client_factory,
        )

    return TerminalHandoffMonitor(
        settings,
        scanner=scanner,
        connector=connector,
        on_event=on_event,
        on_error=on_error,
    )
