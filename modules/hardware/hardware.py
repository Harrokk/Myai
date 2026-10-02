import json
import platform
import subprocess
from pathlib import Path


def _run_command(command, encoding=None):
    options = {
        "capture_output": True,
        "timeout": 20,
    }

    if encoding:
        options["encoding"] = encoding
        options["errors"] = "replace"
    else:
        options["text"] = True

    return subprocess.run(
        command,
        **options,
    )


def _normalize_device(category, name, device_id, status, source):
    return {
        "category": (category or "Unknown").strip(),
        "name": (name or "Okänd enhet").strip(),
        "id": (device_id or "").strip(),
        "status": (status or "").strip(),
        "source": source,
    }


def _windows_inventory():
    result = _run_command(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            (
                "$OutputEncoding = "
                "[Console]::OutputEncoding = "
                "[System.Text.Encoding]::UTF8; "
                "Get-PnpDevice -PresentOnly | "
                "Select-Object Class,FriendlyName,InstanceId,Status | "
                "ConvertTo-Json -Compress"
            ),
        ],
        encoding="utf-8",
    )

    if result.returncode != 0:
        error = result.stderr.strip()
        raise RuntimeError(
            error or "Kunde inte läsa Windows PnP-enheter."
        )

    raw = result.stdout.strip()

    if not raw:
        return []

    parsed = json.loads(raw)

    if isinstance(parsed, dict):
        parsed = [parsed]

    devices = []

    for item in parsed:
        devices.append(
            _normalize_device(
                item.get("Class"),
                item.get("FriendlyName"),
                item.get("InstanceId"),
                item.get("Status"),
                "windows-pnp",
            )
        )

    return devices


def _linux_inventory():
    devices = []

    commands = [
        (["lsusb"], "USB", "linux-lsusb"),
        (["lspci", "-mm"], "PCI", "linux-lspci"),
    ]

    for command, category, source in commands:
        try:
            result = _run_command(command)
        except FileNotFoundError:
            continue

        if result.returncode != 0:
            continue

        for line in result.stdout.splitlines():
            line = line.strip()

            if line:
                devices.append(
                    _normalize_device(
                        category,
                        line,
                        line,
                        "",
                        source,
                    )
                )

    return devices


def _macos_inventory():
    result = _run_command(
        [
            "system_profiler",
            "-json",
            "SPUSBDataType",
            "SPBluetoothDataType",
        ]
    )

    if result.returncode != 0:
        error = result.stderr.strip()
        raise RuntimeError(
            error or "Kunde inte läsa macOS hårdvaruinformation."
        )

    raw = result.stdout.strip()

    if not raw:
        return []

    parsed = json.loads(raw)
    devices = []

    def walk(value, category):
        if isinstance(value, dict):
            name = value.get("_name")

            if name:
                devices.append(
                    _normalize_device(
                        category,
                        name,
                        value.get("serial_num", ""),
                        "",
                        "macos-system-profiler",
                    )
                )

            for child in value.values():
                walk(child, category)

        elif isinstance(value, list):
            for child in value:
                walk(child, category)

    for key, value in parsed.items():
        category = (
            "Bluetooth"
            if "Bluetooth" in key
            else "USB"
        )
        walk(value, category)

    return devices


def get_hardware_inventory():
    """Returnera en normaliserad snapshot av närvarande hårdvara."""
    system = platform.system()

    if system == "Windows":
        return _windows_inventory()

    if system == "Linux":
        return _linux_inventory()

    if system == "Darwin":
        return _macos_inventory()

    return []


def _device_key(device):
    return (
        device.get("id")
        or f"{device.get('category', '')}|{device.get('name', '')}"
    )


def compare_hardware_snapshots(previous, current):
    """Jämför två normaliserade snapshots."""
    previous_map = {
        _device_key(device): device
        for device in previous
    }
    current_map = {
        _device_key(device): device
        for device in current
    }

    added = [
        current_map[key]
        for key in current_map.keys() - previous_map.keys()
    ]
    removed = [
        previous_map[key]
        for key in previous_map.keys() - current_map.keys()
    ]
    changed = []

    for key in current_map.keys() & previous_map.keys():
        before = previous_map[key]
        after = current_map[key]

        if (
            before.get("status") != after.get("status")
            or before.get("name") != after.get("name")
            or before.get("category") != after.get("category")
        ):
            changed.append(
                {
                    "before": before,
                    "after": after,
                }
            )

    return {
        "added": sorted(added, key=lambda item: item["name"]),
        "removed": sorted(removed, key=lambda item: item["name"]),
        "changed": sorted(
            changed,
            key=lambda item: item["after"]["name"],
        ),
    }


def _default_snapshot_path():
    project_root = Path(__file__).resolve().parents[2]
    return project_root / "runtime" / "hardware_snapshot.json"


def load_hardware_snapshot(path=None):
    snapshot_path = Path(path) if path else _default_snapshot_path()

    if not snapshot_path.exists():
        return []

    with snapshot_path.open("r", encoding="utf-8") as file:
        data = json.load(file)

    return data if isinstance(data, list) else []


def save_hardware_snapshot(devices, path=None):
    snapshot_path = Path(path) if path else _default_snapshot_path()
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)

    with snapshot_path.open("w", encoding="utf-8") as file:
        json.dump(
            devices,
            file,
            ensure_ascii=False,
            indent=2,
        )

    return snapshot_path


def hardware_changes(snapshot_path=None):
    """Jämför aktuell hårdvara med föregående lokala snapshot."""
    try:
        current = get_hardware_inventory()
        previous = load_hardware_snapshot(snapshot_path)

        if not previous:
            save_hardware_snapshot(current, snapshot_path)
            return (
                "Hårdvarubaslinje skapad. "
                f"{len(current)} enheter registrerades."
            )

        changes = compare_hardware_snapshots(
            previous,
            current,
        )

        save_hardware_snapshot(current, snapshot_path)

        if not any(changes.values()):
            return "Ingen förändring i hårdvaran upptäcktes."

        lines = ["Hårdvaruförändringar upptäckta:"]

        for device in changes["added"]:
            lines.append(
                f"+ Ny: [{device['category']}] {device['name']}"
            )

        for device in changes["removed"]:
            lines.append(
                f"- Borttagen: [{device['category']}] {device['name']}"
            )

        for item in changes["changed"]:
            before = item["before"]
            after = item["after"]
            lines.append(
                "~ Ändrad: "
                f"[{after['category']}] {after['name']} "
                f"({before.get('status') or 'okänd'} -> "
                f"{after.get('status') or 'okänd'})"
            )

        return "\n".join(lines)

    except Exception as error:
        return f"Fel vid kontroll av hårdvaruförändringar: {error}"


def hardware_inventory():
    """Visa en kompakt lista över närvarande hårdvara."""
    try:
        devices = get_hardware_inventory()

        if not devices:
            return "Ingen hårdvara kunde identifieras."

        grouped = {}

        for device in devices:
            grouped.setdefault(
                device["category"],
                [],
            ).append(device)

        lines = [
            f"Identifierade hårdvaruenheter: {len(devices)}"
        ]

        for category in sorted(grouped):
            lines.append("")
            lines.append(f"{category}:")

            for device in grouped[category][:25]:
                status = (
                    f" [{device['status']}]"
                    if device["status"]
                    else ""
                )
                lines.append(
                    f"- {device['name']}{status}"
                )

            if len(grouped[category]) > 25:
                remaining = len(grouped[category]) - 25
                lines.append(
                    f"- ... ytterligare {remaining} enheter"
                )

        return "\n".join(lines)

    except FileNotFoundError:
        return (
            "Operativsystemets verktyg för hårdvaruinventering "
            "hittades inte."
        )

    except json.JSONDecodeError as error:
        return f"Kunde inte tolka hårdvaruinformation: {error}"

    except subprocess.TimeoutExpired:
        return "Hårdvaruinventeringen tog för lång tid och avbröts."

    except Exception as error:
        return f"Fel vid hårdvaruinventering: {error}"


TOOLS = {
    "hardware_inventory": {
        "function": hardware_inventory,
        "description": (
            "Visar en generell inventering av närvarande hårdvara "
            "och anslutna enheter."
        ),
    },
    "hardware_changes": {
        "function": hardware_changes,
        "description": (
            "Jämför aktuell hårdvara med föregående lokala snapshot "
            "och visar nya, borttagna eller ändrade enheter."
        ),
    },
}
