from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.config import load_settings
from core.terminal_connector_factory import (
    build_terminal_connector,
)


def main():
    settings = load_settings()
    config = settings.get(
        "trusted_terminals",
        {},
    )
    terminals = [
        item
        for item in config.get(
            "terminals",
            [],
        )
        if (
            item.get("id")
            and item.get("trusted")
            and (
                item.get("transport")
                or ""
            ).strip().lower()
            == "bleak_gatt"
        )
    ]

    print("=" * 60)
    print("MyAI BLE GATT connector test")
    print("=" * 60)
    print(
        "Detta test gör en RIKTIG Bluetooth GATT-anslutning "
        "och kopplar sedan från igen."
    )
    print()

    if (
        config.get(
            "connector_provider",
            "none",
        )
        != "bleak_gatt"
    ):
        print(
            "SKIP: connector_provider är inte bleak_gatt."
        )
        return 2

    if not terminals:
        print(
            "SKIP: Ingen betrodd terminal med transport=bleak_gatt "
            "är konfigurerad."
        )
        return 2

    print("Tillgängliga testterminaler:")

    for index, terminal in enumerate(
        terminals,
        start=1,
    ):
        print(
            f"{index}. "
            f"{terminal.get('name') or terminal.get('label') or terminal['id']} "
            f"| id={terminal['id']} "
            f"| service_uuid={terminal.get('service_uuid') or 'SAKNAS'}"
        )

    print()
    choice = input(
        "Ange numret på terminalen som ska testas: "
    ).strip()

    try:
        index = int(choice) - 1
        terminal = terminals[index]
    except (ValueError, IndexError):
        print("Ogiltigt val. Ingen anslutning gjordes.")
        return 1

    device_id = terminal["id"]
    expected = f"CONNECT {device_id}"

    print()
    print(
        "För att bekräfta fysisk anslutning, skriv exakt:"
    )
    print(expected)
    confirmation = input("> ").strip()

    if confirmation != expected:
        print(
            "Bekräftelsen matchade inte. Ingen anslutning gjordes."
        )
        return 1

    try:
        connector = build_terminal_connector(
            settings
        )
    except Exception as error:
        print("Kunde inte skapa connector:")
        print(error)
        return 1

    if connector is None:
        print(
            "Ingen connector skapades. Kontrollera connector_provider."
        )
        return 1

    print()
    print("Ansluter...")

    try:
        result = connector.connect(
            device_id
        )
    except Exception as error:
        print("Anslutningen kastade fel:")
        print(error)
        return 1

    print(result)

    if not result.get("success"):
        print(
            "GATT-anslutningen underkändes."
        )
        return 1

    print()
    print("GATT-anslutning verifierad.")
    input(
        "Tryck Enter för att koppla från igen: "
    )

    try:
        disconnected = connector.disconnect(
            device_id
        )
    except Exception as error:
        print("Frånkopplingen kastade fel:")
        print(error)
        return 1

    print(disconnected)

    if not disconnected.get("success"):
        print(
            "Frånkopplingen kunde inte verifieras."
        )
        return 1

    print(
        "BLE GATT connect/disconnect-testet är godkänt."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
