import glob
import platform
from pathlib import Path
import shutil
import socket
import subprocess

import psutil


INTERFACE_GLOBS = {
    "gpio": ["/dev/gpiochip*"],
    "i2c": ["/dev/i2c-*"],
    "spi": ["/dev/spidev*"],
    "uart": [
        "/dev/ttyHS*",
        "/dev/ttyAMA*",
        "/dev/ttyS*",
    ],
}

I2C_ROOT = Path("/sys/bus/i2c/devices")
SPI_ROOT = Path("/sys/bus/spi/devices")
HWMON_ROOT = Path("/sys/class/hwmon")
DEFAULT_LIMIT = 12

RESERVED_DEVICE_NODES = {
    "/dev/ttyHS1": (
        "Arduino Router reserverar denna UART för Linux↔STM32 Bridge/RPC."
    ),
}

HWMON_KINDS = {
    "power": {
        "pattern": "power*_input",
        "scale": 1_000_000.0,
        "unit": "W",
    },
    "voltage": {
        "pattern": "in*_input",
        "scale": 1_000.0,
        "unit": "V",
    },
    "current": {
        "pattern": "curr*_input",
        "scale": 1_000.0,
        "unit": "A",
    },
}


def _is_linux():
    return platform.system().lower() == "linux"


def _unsupported():
    return {
        "supported": False,
        "platform": platform.system(),
    }


def _run(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


def _read_text(path):
    return Path(path).read_text(
        encoding="utf-8"
    ).strip()


def _read_optional(
    path,
    default="",
):
    try:
        return _read_text(
            path
        )
    except (
        OSError,
        UnicodeError,
    ):
        return default


def _driver_name(
    device_path,
):
    driver = (
        Path(
            device_path
        )
        / "driver"
    )

    try:
        if driver.exists():
            return driver.resolve().name
    except OSError:
        pass

    return ""


def collect_ventuno_interfaces():
    """Read-only Linux-side device-node inventory for VENTUNO Q."""

    if not _is_linux():
        return {
            "supported": False,
            "platform": platform.system(),
            "interfaces": {},
        }

    interfaces = {}

    for name, patterns in (
        INTERFACE_GLOBS.items()
    ):
        matches = []

        for pattern in patterns:
            matches.extend(
                glob.glob(
                    pattern
                )
            )

        interfaces[
            name
        ] = sorted(
            value
            for value in set(
                matches
            )
            if value not in RESERVED_DEVICE_NODES
        )

    reserved = [
        {
            "path": path,
            "reason": reason,
        }
        for path, reason in RESERVED_DEVICE_NODES.items()
        if any(
            path in values
            for values in (
                [
                    match
                    for pattern in patterns
                    for match in glob.glob(
                        pattern
                    )
                ]
                for patterns in INTERFACE_GLOBS.values()
            )
        )
    ]

    return {
        "supported": True,
        "platform": platform.system(),
        "interfaces": interfaces,
        "reserved": reserved,
    }


def format_ventuno_interfaces(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-gränssnitt kan inventeras direkt "
            "endast på Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    interfaces = result.get(
        "interfaces",
        {},
    )
    labels = {
        "gpio": "GPIO device nodes",
        "i2c": "I2C",
        "spi": "SPI",
        "uart": "UART/seriell",
    }
    lines = [
        "Arduino VENTUNO Q / Linux-gränssnitt (read-only):"
    ]
    found = False

    for key in (
        "gpio",
        "i2c",
        "spi",
        "uart",
    ):
        devices = interfaces.get(
            key,
            [],
        )
        label = labels[
            key
        ]

        if devices:
            found = True
            lines.append(
                f"- {label}: "
                + ", ".join(
                    devices
                )
            )
        else:
            lines.append(
                f"- {label}: inget enhetsgränssnitt upptäckt"
            )

    reserved = result.get(
        "reserved",
        [],
    )

    for item in reserved:
        lines.append(
            f"- RESERVERAD: {item['path']} — {item['reason']} "
            "MyAI får inte öppna den direkt."
        )

    if not found:
        lines.append(
            "Inga vanliga Linux-enhetsnoder hittades. "
            "Det betyder inte att MCU-I/O saknas; sådan I/O "
            "kan vara exponerad via Arduino Router/RPC i stället."
        )

    lines.append(
        "MyAI öppnar inga GPIO/I2C/SPI/UART-enheter i denna kontroll."
    )
    return "\n".join(
        lines
    )


def _collect_i2c():
    devices = []

    if not I2C_ROOT.exists():
        return devices

    for item in sorted(
        I2C_ROOT.iterdir(),
        key=lambda path: path.name,
    ):
        name = item.name

        if (
            name.startswith(
                "i2c-"
            )
            or "-" not in name
        ):
            continue

        bus, address = name.split(
            "-",
            1,
        )

        if not bus.isdigit():
            continue

        devices.append(
            {
                "bus": "i2c",
                "id": name,
                "controller": bus,
                "address": address,
                "name": _read_optional(
                    item / "name",
                    "okänd I2C-enhet",
                ),
                "driver": _driver_name(
                    item
                ),
            }
        )

    return devices


def _collect_spi():
    devices = []

    if not SPI_ROOT.exists():
        return devices

    for item in sorted(
        SPI_ROOT.iterdir(),
        key=lambda path: path.name,
    ):
        name = item.name

        if (
            not name.startswith(
                "spi"
            )
            or "." not in name
        ):
            continue

        identifier = name[
            3:
        ]
        controller, chip_select = (
            identifier.split(
                ".",
                1,
            )
        )

        if (
            not controller.isdigit()
            or not chip_select.isdigit()
        ):
            continue

        devices.append(
            {
                "bus": "spi",
                "id": name,
                "controller": controller,
                "chip_select": chip_select,
                "name": (
                    _read_optional(
                        item
                        / "modalias"
                    )
                    or _read_optional(
                        item
                        / "uevent"
                    )
                    or "okänd SPI-enhet"
                ),
                "driver": _driver_name(
                    item
                ),
            }
        )

    return devices


def collect_ventuno_bus_devices():
    if not _is_linux():
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


def format_ventuno_bus_devices(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-bussenheter kan inventeras direkt "
            "endast på Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    lines = [
        (
            "Kernel-registrerade I2C/SPI-enheter "
            "på Arduino VENTUNO Q (read-only):"
        )
    ]
    i2c = result.get(
        "i2c",
        [],
    )
    spi = result.get(
        "spi",
        [],
    )

    if i2c:
        lines.append(
            "I2C:"
        )

        for item in i2c:
            driver = (
                f", driver={item['driver']}"
                if item.get(
                    "driver"
                )
                else ""
            )
            lines.append(
                f"- {item['id']}: {item['name']} "
                f"(adress 0x{item['address']}{driver})"
            )
    else:
        lines.append(
            "I2C: inga kernel-registrerade enheter hittades."
        )

    if spi:
        lines.append(
            "SPI:"
        )

        for item in spi:
            driver = (
                f", driver={item['driver']}"
                if item.get(
                    "driver"
                )
                else ""
            )
            lines.append(
                f"- {item['id']}: {item['name']} "
                f"(CS {item['chip_select']}{driver})"
            )
    else:
        lines.append(
            "SPI: inga kernel-registrerade enheter hittades."
        )

    lines.append(
        "Ingen aktiv buss-skanning utfördes."
    )
    return "\n".join(
        lines
    )


def _read_number(
    path,
):
    return float(
        _read_text(
            path
        )
    )


def _label_for(
    input_path,
):
    stem = input_path.name[
        :-len(
            "_input"
        )
    ]
    label_path = (
        input_path.with_name(
            stem
            + "_label"
        )
    )

    try:
        return _read_text(
            label_path
        )
    except (
        OSError,
        UnicodeError,
    ):
        return stem


def collect_ventuno_power_telemetry():
    if not _is_linux():
        return {
            "supported": False,
            "platform": platform.system(),
            "measurements": [],
        }

    measurements = []

    if not HWMON_ROOT.exists():
        return {
            "supported": True,
            "platform": platform.system(),
            "measurements": [],
        }

    for hwmon in sorted(
        HWMON_ROOT.glob(
            "hwmon*"
        )
    ):
        try:
            source = _read_text(
                hwmon / "name"
            )
        except (
            OSError,
            UnicodeError,
        ):
            source = hwmon.name

        for kind, config in (
            HWMON_KINDS.items()
        ):
            for input_path in sorted(
                hwmon.glob(
                    config[
                        "pattern"
                    ]
                )
            ):
                try:
                    raw = _read_number(
                        input_path
                    )
                except (
                    OSError,
                    UnicodeError,
                    ValueError,
                ):
                    continue

                measurements.append(
                    {
                        "kind": kind,
                        "source": source,
                        "label": _label_for(
                            input_path
                        ),
                        "value": (
                            raw
                            / config[
                                "scale"
                            ]
                        ),
                        "unit": config[
                            "unit"
                        ],
                        "path": str(
                            input_path
                        ),
                    }
                )

    return {
        "supported": True,
        "platform": platform.system(),
        "measurements": measurements,
    }


def format_ventuno_power_telemetry(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-strömtelemetri kräver Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    measurements = result.get(
        "measurements",
        [],
    )

    if not measurements:
        return (
            "Ingen effekt-, spännings- eller strömtelemetri "
            "exponerades via Linux hwmon. "
            "MyAI gör därför ingen uppskattning."
        )

    lines = [
        "Arduino VENTUNO Q / Linux hwmon-telemetri:"
    ]

    for item in measurements:
        lines.append(
            f"- {item['source']} / {item['label']}: "
            f"{item['value']:.3f} {item['unit']} "
            f"({item['kind']})"
        )

    return "\n".join(
        lines
    )


def collect_ventuno_network_status():
    if not _is_linux():
        return _unsupported()

    stats = psutil.net_if_stats()
    interfaces = []

    for name, addresses in (
        psutil.net_if_addrs().items()
    ):
        info = stats.get(
            name
        )
        normalized = []

        for address in addresses:
            if (
                address.family
                == socket.AF_INET
            ):
                kind = "ipv4"
            elif (
                address.family
                == socket.AF_INET6
            ):
                kind = "ipv6"
            else:
                continue

            normalized.append(
                {
                    "type": kind,
                    "address": (
                        address.address.split(
                            "%",
                            1,
                        )[0]
                    ),
                }
            )

        interfaces.append(
            {
                "name": name,
                "up": (
                    bool(
                        info.isup
                    )
                    if info
                    else None
                ),
                "speed_mbps": (
                    info.speed
                    if (
                        info
                        and info.speed > 0
                    )
                    else None
                ),
                "addresses": normalized,
            }
        )

    interfaces.sort(
        key=lambda item: item[
            "name"
        ]
    )

    return {
        "supported": True,
        "platform": platform.system(),
        "interfaces": interfaces,
    }


def collect_ventuno_process_status(
    limit=DEFAULT_LIMIT,
):
    if not _is_linux():
        return _unsupported()

    processes = []

    for process in psutil.process_iter(
        [
            "pid",
            "name",
            "cpu_percent",
            "memory_percent",
            "username",
        ]
    ):
        try:
            item = dict(
                process.info
            )
        except (
            psutil.NoSuchProcess,
            psutil.AccessDenied,
        ):
            continue

        item[
            "cpu_percent"
        ] = float(
            item.get(
                "cpu_percent"
            )
            or 0.0
        )
        item[
            "memory_percent"
        ] = float(
            item.get(
                "memory_percent"
            )
            or 0.0
        )
        processes.append(
            item
        )

    processes.sort(
        key=lambda item: (
            item[
                "memory_percent"
            ],
            item[
                "cpu_percent"
            ],
        ),
        reverse=True,
    )

    return {
        "supported": True,
        "platform": platform.system(),
        "processes": processes[
            : max(
                1,
                int(
                    limit
                ),
            )
        ],
    }


def collect_ventuno_services_status(
    limit=DEFAULT_LIMIT,
):
    if not _is_linux():
        return _unsupported()

    if not shutil.which(
        "systemctl"
    ):
        return {
            "supported": True,
            "available": False,
            "services": [],
            "reason": "systemctl saknas",
        }

    result = _run(
        [
            "systemctl",
            "list-units",
            "--type=service",
            "--state=running",
            "--no-legend",
            "--no-pager",
        ]
    )

    if result.returncode != 0:
        return {
            "supported": True,
            "available": False,
            "services": [],
            "reason": (
                result.stderr.strip()
                or "systemctl misslyckades"
            ),
        }

    services = []

    for line in (
        result.stdout.splitlines()
    ):
        line = line.strip()

        if not line:
            continue

        parts = line.split(
            None,
            4,
        )
        services.append(
            {
                "unit": parts[
                    0
                ],
                "description": (
                    parts[
                        4
                    ]
                    if len(
                        parts
                    )
                    > 4
                    else ""
                ),
            }
        )

    return {
        "supported": True,
        "available": True,
        "services": services[
            : max(
                1,
                int(
                    limit
                ),
            )
        ],
    }


def collect_ventuno_system_logs(
    limit=DEFAULT_LIMIT,
):
    if not _is_linux():
        return _unsupported()

    if not shutil.which(
        "journalctl"
    ):
        return {
            "supported": True,
            "available": False,
            "entries": [],
            "reason": "journalctl saknas",
        }

    result = _run(
        [
            "journalctl",
            "-p",
            "warning",
            "-n",
            str(
                max(
                    1,
                    int(
                        limit
                    ),
                )
            ),
            "--no-pager",
            "--output=short-iso",
        ]
    )

    if result.returncode != 0:
        return {
            "supported": True,
            "available": False,
            "entries": [],
            "reason": (
                result.stderr.strip()
                or "journalctl misslyckades"
            ),
        }

    entries = [
        line.strip()
        for line in (
            result.stdout.splitlines()
        )
        if (
            line.strip()
            and not line.startswith(
                "-- "
            )
        )
    ]

    return {
        "supported": True,
        "available": True,
        "entries": entries[
            -max(
                1,
                int(
                    limit
                ),
            ):
        ],
    }


def format_ventuno_network_status(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-nätverksstatus kräver Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    lines = [
        "Arduino VENTUNO Q nätverksgränssnitt:"
    ]

    for interface in result.get(
        "interfaces",
        [],
    ):
        state = (
            "up"
            if interface.get(
                "up"
            )
            else "down"
        )
        addresses = ", ".join(
            f"{item['type']}={item['address']}"
            for item in interface.get(
                "addresses",
                [],
            )
        ) or "ingen IP-adress"
        speed = interface.get(
            "speed_mbps"
        )
        suffix = (
            f", {speed} Mbit/s"
            if speed
            else ""
        )
        lines.append(
            f"- {interface['name']}: "
            f"{state}{suffix}, {addresses}"
        )

    if len(
        lines
    ) == 1:
        lines.append(
            "- Inga nätverksgränssnitt hittades."
        )

    return "\n".join(
        lines
    )


def format_ventuno_process_status(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-processstatus kräver Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    lines = [
        "Processer med högst minnesanvändning:"
    ]

    for item in result.get(
        "processes",
        [],
    ):
        lines.append(
            f"- PID {item.get('pid')}: "
            f"{item.get('name') or 'okänd'} | "
            f"CPU {item.get('cpu_percent', 0):.1f}% | "
            f"RAM {item.get('memory_percent', 0):.1f}%"
        )

    return "\n".join(
        lines
    )


def format_ventuno_services_status(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-tjänststatus kräver Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    if not result.get(
        "available",
        False,
    ):
        return (
            "Tjänststatus kunde inte läsas: "
            + result.get(
                "reason",
                "okänd orsak",
            )
        )

    lines = [
        "Körande systemd-tjänster:"
    ]

    for service in result.get(
        "services",
        [],
    ):
        suffix = (
            f" - {service['description']}"
            if service.get(
                "description"
            )
            else ""
        )
        lines.append(
            f"- {service.get('unit')}{suffix}"
        )

    return "\n".join(
        lines
    )


def format_ventuno_system_logs(
    result,
):
    if not result.get(
        "supported"
    ):
        return (
            "VENTUNO-systemloggar kräver Linux. "
            f"Nuvarande plattform: "
            f"{result.get('platform') or 'okänd'}."
        )

    if not result.get(
        "available",
        False,
    ):
        return (
            "Systemloggar kunde inte läsas: "
            + result.get(
                "reason",
                "okänd orsak",
            )
        )

    lines = [
        (
            "Senaste journalposter på "
            "warning-nivå eller högre:"
        )
    ]
    lines.extend(
        f"- {entry}"
        for entry in result.get(
            "entries",
            [],
        )
    )

    return "\n".join(
        lines
    )


def ventuno_io_safety():
    return (
        "VENTUNO I/O-säkerhet: MyAI hårdkodar inga fysiska "
        "GPIO-, I2C-, SPI- eller UART-pinnummer i Linux-runtime. "
        "Använd aktuell officiell VENTUNO Q-pinout för fysisk inkoppling "
        "och använd Arduino Router/RPC för MCU-styrning. "
        "Linux-enhetsnoder kan innehålla resurser som ägs av systemtjänster. "
        "/dev/ttyHS1 är reserverad av Arduino Router och får inte öppnas "
        "direkt av MyAI."
    )


def ventuno_interfaces_status():
    try:
        return format_ventuno_interfaces(
            collect_ventuno_interfaces()
        )
    except Exception as error:
        return (
            "Fel vid inventering av VENTUNO-gränssnitt: "
            f"{error}"
        )


def ventuno_bus_devices_status():
    try:
        return format_ventuno_bus_devices(
            collect_ventuno_bus_devices()
        )
    except Exception as error:
        return (
            "Fel vid inventering av VENTUNO-bussenheter: "
            f"{error}"
        )


def ventuno_power_status():
    try:
        return format_ventuno_power_telemetry(
            collect_ventuno_power_telemetry()
        )
    except Exception as error:
        return (
            "Fel vid VENTUNO-strömtelemetri: "
            f"{error}"
        )


def ventuno_network_status():
    try:
        return format_ventuno_network_status(
            collect_ventuno_network_status()
        )
    except Exception as error:
        return (
            "Fel vid VENTUNO-nätverksstatus: "
            f"{error}"
        )


def ventuno_process_status():
    try:
        return format_ventuno_process_status(
            collect_ventuno_process_status()
        )
    except Exception as error:
        return (
            "Fel vid VENTUNO-processstatus: "
            f"{error}"
        )


def ventuno_services_status():
    try:
        return format_ventuno_services_status(
            collect_ventuno_services_status()
        )
    except Exception as error:
        return (
            "Fel vid VENTUNO-tjänststatus: "
            f"{error}"
        )


def ventuno_system_logs():
    try:
        return format_ventuno_system_logs(
            collect_ventuno_system_logs()
        )
    except Exception as error:
        return (
            "Fel vid VENTUNO-systemloggar: "
            f"{error}"
        )


TOOLS = {
    "ventuno_interfaces_status": {
        "function": ventuno_interfaces_status,
        "description": (
            "Inventerar read-only Linux-enhetsnoder för GPIO/I2C/SPI/UART "
            "på Arduino VENTUNO Q utan att öppna eller konfigurera dem."
        ),
    },
    "ventuno_bus_devices_status": {
        "function": ventuno_bus_devices_status,
        "description": (
            "Listar read-only kernel-registrerade I2C- och SPI-enheter "
            "på Arduino VENTUNO Q utan aktiv buss-skanning."
        ),
    },
    "ventuno_power_status": {
        "function": ventuno_power_status,
        "description": (
            "Läser read-only effekt, spänning och ström från Linux hwmon "
            "på Arduino VENTUNO Q när drivrutiner exponerar mätvärden."
        ),
    },
    "ventuno_network_status": {
        "function": ventuno_network_status,
        "description": (
            "Visar read-only nätverksgränssnitt och IP-adresser "
            "på Arduino VENTUNO Q Linux."
        ),
    },
    "ventuno_process_status": {
        "function": ventuno_process_status,
        "description": (
            "Visar read-only processöversikt med CPU- och RAM-användning "
            "på Arduino VENTUNO Q Linux."
        ),
    },
    "ventuno_services_status": {
        "function": ventuno_services_status,
        "description": (
            "Visar read-only körande systemd-tjänster "
            "på Arduino VENTUNO Q Linux."
        ),
    },
    "ventuno_system_logs": {
        "function": ventuno_system_logs,
        "description": (
            "Visar read-only senaste systemd-journalposter "
            "på warning-nivå eller högre."
        ),
    },
    "ventuno_io_safety": {
        "function": ventuno_io_safety,
        "description": (
            "Förklarar säker VENTUNO I/O-policy utan att gissa "
            "fysiska pinnummer."
        ),
    },
}
