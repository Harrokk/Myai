import time
from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.config import load_settings
from core.hardware_monitor import (
    HardwareMonitor,
    format_hardware_changes,
)
from modules.hardware.hardware import get_hardware_inventory


def on_change(changes):
    print()
    print("=" * 60)
    print("HÅRDVARUFÖRÄNDRING")
    print("=" * 60)
    print(format_hardware_changes(changes))
    print()


def on_error(error):
    print()
    print(f"FEL: {error}")
    print()


def main():
    settings = load_settings()
    watch_settings = settings.get("hardware_watch", {})
    interval = watch_settings.get("interval_seconds", 10)

    print("=" * 60)
    print("MyAI hardware watch test")
    print("=" * 60)

    baseline = get_hardware_inventory()
    print(f"Baseline: {len(baseline)} enheter")
    print(f"Kontrollintervall: {interval} sekunder")
    print()
    print(
        "Koppla nu in eller ur en USB-enhet. "
        "Testet kör tills du trycker Ctrl+C."
    )
    print()

    monitor = HardwareMonitor(
        interval_seconds=interval,
        on_change=on_change,
        on_error=on_error,
    )

    if not monitor.start():
        print("Kunde inte starta hårdvaruövervakningen.")
        return 1

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print()
        print("Stoppar övervakningen...")
    finally:
        monitor.stop()

    print("Hårdvaruövervakningen stoppad.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
