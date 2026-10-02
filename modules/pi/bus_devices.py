from pathlib import Path
import platform


I2C_ROOT = Path("/sys/bus/i2c/devices")
SPI_ROOT = Path("/sys/bus/spi/devices")


def _read_optional(path, default=""):
    try:
        return Path(path).read_text(encoding="utf-8").strip()
    except (OSError, UnicodeError):
        return default


def _driver_name(device_path):
    driver = Path(device_path) / "driver"

    try:
        if driver.exists():
            return driver.resolve().name
    except OSError:
        pass

    return ""


def _collect_i2c():
    devices = []

    if not I2C_ROOT.exists():
        return devices

    for item in sorted(I2C_ROOT.iterdir(), key=lambda path: path.name):
        name = item.name

        if name.startswith("i2c-"):
            continue

        if "-" not in name:
            continue

        bus, address = name.split("-", 1)

        if not bus.isdigit():
            continue

        devices.append(
            {
                "bus": "i2c",
                "id": name,
                "controller": bus,
                "address": address,
                "name": _read_optional(item / "name", "okänd I2C-enhet"),
                "driver": _driver_name(item),
            }
        )

    return devices


def _collect_spi():
    devices = []

    if not SPI_ROOT.exists():
        return devices

    for item in sorted(SPI_ROOT.iterdir(), key=lambda path: path.name):
        name = item.name

        if not name.startswith("spi") or "." not in name:
            continue

        identifier = name[3:]
        controller, chip_select = identifier.split(".", 1)

        if not controller.isdigit() or not chip_select.isdigit():
            continue

        devices.append(
            {
                "bus": "spi",
                "id": name,
                "controller": controller,
                "chip_select": chip_select,
                "name": (
                    _read_optional(item / "modalias")
                    or _read_optional(item / "uevent")
                    or "okänd SPI-enhet"
                ),
                "driver": _driver_name(item),
            }
        )

    return devices


def collect_bus_devices():
    if platform.system().lower() != "linux":
        return {
            "supported": False,
            "platform": platform.system(),
            "i2c": [],
            "spi": [],
        }

    return {
        "supported": True,
        "platform": platform.system(),
        "i2c": _collect_i2c(),
        "spi": _collect_spi(),
    }


def format_bus_devices(result):
    if not result.get("supported"):
        return (
            "Pi-bussenheter kan endast inventeras direkt på Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    lines = ["Kernel-registrerade Pi-bussenheter (read-only):"]

    i2c = result.get("i2c", [])
    spi = result.get("spi", [])

    if i2c:
        lines.append("I2C:")

        for item in i2c:
            driver = f", driver={item['driver']}" if item.get("driver") else ""
            lines.append(
                f"- {item['id']}: {item['name']} "
                f"(adress 0x{item['address']}{driver})"
            )
    else:
        lines.append("I2C: inga kernel-registrerade enheter hittades.")

    if spi:
        lines.append("SPI:")

        for item in spi:
            driver = f", driver={item['driver']}" if item.get("driver") else ""
            lines.append(
                f"- {item['id']}: {item['name']} "
                f"(CS {item['chip_select']}{driver})"
            )
    else:
        lines.append("SPI: inga kernel-registrerade enheter hittades.")

    lines.append(
        "Ingen aktiv buss-skanning utfördes; listan visar bara enheter som "
        "Linux-kärnan redan känner till."
    )
    return "\n".join(lines)


def pi_bus_devices_status():
    try:
        return format_bus_devices(collect_bus_devices())
    except Exception as error:
        return f"Fel vid inventering av Pi-bussenheter: {error}"


TOOLS = {
    "pi_bus_devices_status": {
        "function": pi_bus_devices_status,
        "description": (
            "Listar read-only kernel-registrerade I2C- och SPI-enheter "
            "på Linux/Raspberry Pi utan aktiv buss-skanning."
        ),
    }
}
