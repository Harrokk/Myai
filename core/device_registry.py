import json
from copy import deepcopy
from pathlib import Path
import threading

from core.config import PROJECT_ROOT


DEFAULT_REGISTRY_PATH = PROJECT_ROOT / "runtime" / "device_registry.json"


def _device_key(device):
    device_id = (device.get("id") or "").strip()

    if device_id:
        return device_id

    return "|".join(
        [
            (device.get("category") or "Unknown").strip(),
            (device.get("name") or "Okänd enhet").strip(),
            (device.get("source") or "unknown").strip(),
        ]
    )


def _record_from_device(device, key):
    return {
        "key": key,
        "id": (device.get("id") or "").strip(),
        "category": (device.get("category") or "Unknown").strip(),
        "name": (device.get("name") or "Okänd enhet").strip(),
        "status": (device.get("status") or "").strip(),
        "source": (device.get("source") or "unknown").strip(),
        "known": False,
        "label": "",
        "configuration_status": "pending",
    }


def format_device_records(records):
    if not records:
        return "Inga registrerade enheter."

    lines = []

    for record in records:
        state = "känd" if record.get("known") else "okänd"
        label = record.get("label") or record.get("name") or "Okänd enhet"
        lines.append(
            f"- [{state}] [{record.get('category') or 'Unknown'}] "
            f"{label} | id={record['key']}"
        )

    return "\n".join(lines)


class DeviceRegistry:
    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_REGISTRY_PATH
        self._lock = threading.Lock()

    @staticmethod
    def _empty_data():
        return {
            "version": 2,
            "devices": {},
        }

    def _load_unlocked(self):
        if not self.path.exists():
            return self._empty_data()

        with self.path.open("r", encoding="utf-8") as file:
            data = json.load(file)

        if not isinstance(data, dict):
            raise ValueError("Enhetsregistret måste innehålla ett JSON-objekt.")

        devices = data.get("devices")

        if not isinstance(devices, dict):
            raise ValueError("Enhetsregistret saknar ett giltigt devices-objekt.")

        normalized = {}

        for key, record in devices.items():
            item = deepcopy(record)
            item.setdefault(
                "configuration_status",
                "approved" if item.get("known") else "pending",
            )
            normalized[key] = item

        return {
            "version": 2,
            "devices": normalized,
        }

    def _save_unlocked(self, data):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + ".tmp")

        with temporary.open("w", encoding="utf-8") as file:
            json.dump(
                data,
                file,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )

        temporary.replace(self.path)

    def observe_devices(self, devices):
        new_records = []

        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]
            changed = False

            for device in devices:
                key = _device_key(device)

                if key not in registry:
                    registry[key] = _record_from_device(device, key)
                    new_records.append(deepcopy(registry[key]))
                    changed = True
                    continue

                record = registry[key]

                for field in ("id", "category", "name", "status", "source"):
                    value = (device.get(field) or "").strip()

                    if field in ("category", "name") and not value:
                        continue

                    if record.get(field) != value:
                        record[field] = value
                        changed = True

            if changed:
                self._save_unlocked(data)

        return new_records

    def observe_changes(self, changes):
        return self.observe_devices(changes.get("added", []))

    def list_records(self, known=None):
        with self._lock:
            data = self._load_unlocked()

        records = list(data["devices"].values())

        if known is not None:
            records = [
                record
                for record in records
                if bool(record.get("known")) is bool(known)
            ]

        return sorted(
            (deepcopy(record) for record in records),
            key=lambda record: (
                record.get("category") or "",
                record.get("name") or "",
                record.get("key") or "",
            ),
        )

    def get_record(self, key):
        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]

            if key not in registry:
                raise KeyError(key)

            return deepcopy(registry[key])

    def list_pending(self):
        return [
            record
            for record in self.list_records()
            if record.get("configuration_status") == "pending"
        ]

    def approve_configuration(self, key, label=None):
        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]

            if key not in registry:
                raise KeyError(key)

            registry[key]["known"] = True
            registry[key]["configuration_status"] = "approved"

            if label is not None:
                registry[key]["label"] = label.strip()

            self._save_unlocked(data)
            return deepcopy(registry[key])

    def reject_configuration(self, key):
        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]

            if key not in registry:
                raise KeyError(key)

            registry[key]["known"] = False
            registry[key]["configuration_status"] = "rejected"
            self._save_unlocked(data)
            return deepcopy(registry[key])

    def mark_known(self, key, label=None):
        return self.approve_configuration(key, label=label)


def format_configuration_prompt(record):
    label = record.get("label") or record.get("name") or "Okänd enhet"
    category = record.get("category") or "Unknown"
    key = record.get("key") or record.get("id") or ""

    return (
        f"Ny okänd enhet: [{category}] {label}\n"
        f"Vill du konfigurera den?\n"
        f"Godkänn: /device approve {key}\n"
        f"Avvisa: /device reject {key}"
    )
