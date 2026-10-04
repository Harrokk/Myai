from copy import deepcopy
from pathlib import Path
import sys
import time


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.config import load_settings
from core.terminal_handoff import (
    TerminalHandoffMonitor,
    format_terminal_handoff_event,
)
from modules.bluetooth.proximity import (
    format_nearby_devices,
    scan_nearby_devices,
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
        if item.get("id")
    ]

    print("=" * 60)
    print("MyAI trusted-terminal handoff test")
    print("=" * 60)
    print(
        "Detta test tvingar auto_execute=false. "
        "Ingen Bluetooth-anslutning utförs."
    )
    print()

    if not terminals:
        print(
            "Ingen terminal är konfigurerad ännu. "
            "Jag gör en BLE-skanning så du kan se kandidat-ID:n."
        )
        print()
        observations = scan_nearby_devices(
            timeout=5.0
        )
        print(
            format_nearby_devices(
                observations
            )
        )
        print()
        print(
            "Lägg sedan rätt device-id i "
            "trusted_terminals.terminals och kör testet igen."
        )
        return 2

    test_settings = deepcopy(settings)
    test_config = test_settings[
        "trusted_terminals"
    ]
    test_config["enabled"] = True
    test_config["auto_execute"] = False

    events = []

    def on_event(event):
        events.append(event)
        print()
        print(
            format_terminal_handoff_event(
                event
            )
        )
        print()

    def on_error(error):
        print()
        print("Bluetooth handoff-fel:")
        print(error)
        print()

    monitor = TerminalHandoffMonitor(
        test_settings,
        on_event=on_event,
        on_error=on_error,
    )

    print("Konfigurerade terminaler:")

    for terminal in terminals:
        print(
            "-",
            terminal.get("name")
            or terminal.get("label")
            or terminal["id"],
            "|",
            terminal["id"],
        )

    print()
    print(
        "Skanningsintervall:",
        monitor.interval_seconds,
        "sekunder",
    )
    print(
        "Connect kräver",
        monitor.connect_confirm_scans,
        "starka skanningar.",
    )
    print(
        "Disconnect kräver",
        monitor.disconnect_confirm_scans,
        "svaga/missade skanningar.",
    )
    print()
    print(
        "Flytta terminalen nära och långt bort. "
        "Avsluta med Ctrl+C."
    )

    if not monitor.start():
        print(
            "Monitorn kunde inte startas. "
            "Kontrollera trusted_terminals.enabled/testkonfiguration."
        )
        return 1

    try:
        while monitor.is_running:
            time.sleep(0.5)
    except KeyboardInterrupt:
        print()
        print("Stoppar...")
    finally:
        monitor.stop()

    print(
        f"Totalt registrerade handoff-event: {len(events)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
