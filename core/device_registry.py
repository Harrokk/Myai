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
        "configured": False,
        "label": "",
        "configuration": {},
    }


def _normalize_record(record, key):
    if not isinstance(record, dict):
        raise ValueError(f"Ogiltig enhetspost för {key}.")

    normalized = deepcopy(record)
    normalized.setdefault("key", key)
    normalized.setdefault("id", "")
    normalized.setdefault("category", "Unknown")
    normalized.setdefault("name", "Okänd enhet")
    normalized.setdefault("status", "")
    normalized.setdefault("source", "unknown")
    normalized.setdefault("known", False)
    normalized.setdefault("configured", False)
    normalized.setdefault("label", "")
    normalized.setdefault("configuration", {})

    if not isinstance(normalized["configuration"], dict):
        raise ValueError(
            f"Enhetskonfigurationen för {key} måste vara ett JSON-objekt."
        )

    return normalized


def format_device_records(records):
    if not records:
        return "Inga registrerade enheter."

    lines = []

    for record in records:
        state = "känd" if record.get("known") else "okänd"
        configured = (
            "konfigurerad"
            if record.get("configured")
            else "ej konfigurerad"
        )
        label = record.get("label") or record.get("name") or "Okänd enhet"
        lines.append(
            f"- [{state}] [{configured}] "
            f"[{record.get('category') or 'Unknown'}] "
            f"{label} | id={record['key']}"
        )

    return "\n".join(lines)


def format_device_details(record):
    label = record.get("label") or record.get("name") or "Okänd enhet"
    configuration = record.get("configuration") or {}
    mode = configuration.get("mode", "inte satt")
    auto_actions = configuration.get("auto_actions", False)

    return "\n".join(
        [
            f"Enhet: {label}",
            f"ID: {record.get('key') or 'saknas'}",
            f"Kategori: {record.get('category') or 'Unknown'}",
            f"Källa: {record.get('source') or 'unknown'}",
            f"Status: {record.get('status') or 'okänd'}",
            f"Känd: {'ja' if record.get('known') else 'nej'}",
            f"Konfigurerad: {'ja' if record.get('configured') else 'nej'}",
            f"Konfigurationsläge: {mode}",
            f"Automatiska åtgärder: {'ja' if auto_actions else 'nej'}",
        ]
    )


class DeviceRegistry:
    def __init__(self, path=None):
        self.path = Path(path) if path else DEFAULT_REGISTRY_PATH
        self._lock = threading.Lock()

    @staticmethod
    def _empty_data():
        return {
            "version": 1,
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

        normalized_devices = {
            key: _normalize_record(record, key)
            for key, record in devices.items()
        }

        return {
            "version": 1,
            "devices": normalized_devices,
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
            record = data["devices"].get(key)

        if record is None:
            raise KeyError(key)

        return deepcopy(record)

    def mark_known(self, key, label=None):
        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]

            if key not in registry:
                raise KeyError(key)

            registry[key]["known"] = True

            if label is not None:
                registry[key]["label"] = label.strip()

            self._save_unlocked(data)
            return deepcopy(registry[key])

    def propose_configuration(self, key):
        record = self.get_record(key)

        return {
            "device": record,
            "configuration": {
                "mode": "registered_only",
                "auto_actions": False,
            },
            "requires_confirmation": True,
        }

    def approve_configuration(self, key, label=None, configuration=None):
        requested = deepcopy(configuration or {})

        if not isinstance(requested, dict):
            raise ValueError("Konfigurationen måste vara ett JSON-objekt.")

        requested.setdefault("mode", "registered_only")
        requested.setdefault("auto_actions", False)

        if requested.get("auto_actions") is not False:
            raise ValueError(
                "Automatiska åtgärder kräver ett separat framtida godkännandeflöde."
            )

        with self._lock:
            data = self._load_unlocked()
            registry = data["devices"]

            if key not in registry:
                raise KeyError(key)

            record = registry[key]
            record["known"] = True
            record["configured"] = True
            record["configuration"] = requested

            if label is not None:
                record["label"] = label.strip()

            self._save_unlocked(data)
            return deepcopy(record)
