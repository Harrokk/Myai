import threading

from modules.hardware.hardware import (
    compare_hardware_snapshots,
    get_hardware_inventory,
)


def has_hardware_changes(changes):
    return any(
        changes.get(key)
        for key in ("added", "removed", "changed")
    )


def format_hardware_changes(changes):
    lines = []

    for device in changes.get("added", []):
        lines.append(
            f"+ Ny: [{device['category']}] {device['name']}"
        )

    for device in changes.get("removed", []):
        lines.append(
            f"- Borttagen: [{device['category']}] {device['name']}"
        )

    for item in changes.get("changed", []):
        before = item["before"]
        after = item["after"]
        lines.append(
            "~ Ändrad: "
            f"[{after['category']}] {after['name']} "
            f"({before.get('status') or 'okänd'} -> "
            f"{after.get('status') or 'okänd'})"
        )

    return "\n".join(lines)


class HardwareMonitor:
    def __init__(
        self,
        interval_seconds=10,
        inventory_reader=None,
        on_change=None,
        on_error=None,
    ):
        self.interval_seconds = max(
            float(interval_seconds),
            1.0,
        )
        self.inventory_reader = (
            inventory_reader
            or get_hardware_inventory
        )
        self.on_change = on_change
        self.on_error = on_error

        self._previous = None
        self._stop_event = threading.Event()
        self._thread = None

    @property
    def is_running(self):
        return bool(
            self._thread
            and self._thread.is_alive()
        )

    def establish_baseline(self):
        self._previous = self.inventory_reader()
        return self._previous

    def poll_once(self):
        current = self.inventory_reader()

        if self._previous is None:
            self._previous = current
            return {
                "added": [],
                "removed": [],
                "changed": [],
            }

        changes = compare_hardware_snapshots(
            self._previous,
            current,
        )
        self._previous = current

        if (
            has_hardware_changes(changes)
            and self.on_change is not None
        ):
            self.on_change(changes)

        return changes

    def start(self):
        if self.is_running:
            return False

        self._stop_event.clear()

        try:
            self.establish_baseline()
        except Exception as error:
            if self.on_error is not None:
                self.on_error(error)
            return False

        self._thread = threading.Thread(
            target=self._run,
            name="MyAI-HardwareMonitor",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self, timeout=2):
        self._stop_event.set()

        if self._thread is not None:
            self._thread.join(timeout=timeout)

        return not self.is_running

    def _run(self):
        while not self._stop_event.wait(
            self.interval_seconds
        ):
            try:
                self.poll_once()
            except Exception as error:
                if self.on_error is not None:
                    self.on_error(error)
