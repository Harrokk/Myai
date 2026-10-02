import glob
import platform


INTERFACE_GLOBS = {
    "gpio": ["/dev/gpiochip*"],
    "i2c": ["/dev/i2c-*"],
    "spi": ["/dev/spidev*"],
    "uart": ["/dev/ttyAMA*", "/dev/ttyS*"],
}


def _unique_sorted(items):
    return sorted(set(items))


def collect_pi_interfaces():
    """Read-only discovery of common Raspberry Pi/Linux hardware interfaces."""
    if platform.system().lower() != "linux":
        return {
            "supported": False,
            "platform": platform.system(),
            "interfaces": {},
        }

    interfaces = {}

    for name, patterns in INTERFACE_GLOBS.items():
        matches = []

        for pattern in patterns:
            matches.extend(glob.glob(pattern))

        interfaces[name] = _unique_sorted(matches)

    return {
        "supported": True,
        "platform": platform.system(),
        "interfaces": interfaces,
    }


def format_pi_interfaces(result):
    if not result.get("supported"):
        return (
            "Pi-gränssnitt kan endast inventeras direkt på Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    interfaces = result.get("interfaces", {})
    lines = ["Tillgängliga Linux/Pi-gränssnitt:"]

    labels = {
        "gpio": "GPIO",
        "i2c": "I2C",
        "spi": "SPI",
        "uart": "UART/seriell",
    }

    found_any = False

    for key in ("gpio", "i2c", "spi", "uart"):
        devices = interfaces.get(key, [])
        label = labels[key]

        if devices:
            found_any = True
            lines.append(f"- {label}: " + ", ".join(devices))
        else:
            lines.append(f"- {label}: inget enhetsgränssnitt upptäckt")

    if not found_any:
        lines.append(
            "Inga vanliga GPIO/I2C/SPI/UART-enhetsnoder hittades. "
            "Gränssnitt kan vara avstängda eller saknas."
        )

    return "\n".join(lines)


def pi_interfaces_status():
    try:
        return format_pi_interfaces(collect_pi_interfaces())
    except Exception as error:
        return f"Fel vid inventering av Pi-gränssnitt: {error}"


TOOLS = {
    "pi_interfaces_status": {
        "function": pi_interfaces_status,
        "description": (
            "Inventerar read-only tillgängliga GPIO-, I2C-, SPI- och "
            "UART-enhetsgränssnitt på Linux/Raspberry Pi."
        ),
    }
}
