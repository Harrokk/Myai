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
