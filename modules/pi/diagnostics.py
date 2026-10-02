import platform
import shutil
import socket
import subprocess

import psutil


DEFAULT_LIMIT = 12


def _is_linux():
    return platform.system().lower() == "linux"


def _run(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


def _unsupported():
    return {
        "supported": False,
        "platform": platform.system(),
    }


def collect_network_status():
    if not _is_linux():
        return _unsupported()

    stats = psutil.net_if_stats()
    interfaces = []

    for name, addresses in psutil.net_if_addrs().items():
        info = stats.get(name)
        normalized_addresses = []

        for address in addresses:
            if address.family == socket.AF_INET:
                kind = "ipv4"
            elif address.family == socket.AF_INET6:
                kind = "ipv6"
            else:
                continue

            normalized_addresses.append(
                {
                    "type": kind,
                    "address": address.address.split("%", 1)[0],
                }
            )

        interfaces.append(
            {
                "name": name,
                "up": bool(info.isup) if info else None,
                "speed_mbps": info.speed if info and info.speed > 0 else None,
                "addresses": normalized_addresses,
            }
        )

    interfaces.sort(key=lambda item: item["name"])

    return {
        "supported": True,
        "platform": platform.system(),
        "interfaces": interfaces,
    }


def collect_process_status(limit=DEFAULT_LIMIT):
    if not _is_linux():
        return _unsupported()

    processes = []

    for process in psutil.process_iter(
        ["pid", "name", "cpu_percent", "memory_percent", "username"]
    ):
        try:
            item = dict(process.info)
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

        item["cpu_percent"] = float(item.get("cpu_percent") or 0.0)
        item["memory_percent"] = float(item.get("memory_percent") or 0.0)
        processes.append(item)

    processes.sort(
        key=lambda item: (
            item["memory_percent"],
            item["cpu_percent"],
        ),
        reverse=True,
    )

    return {
        "supported": True,
        "platform": platform.system(),
        "processes": processes[: max(1, int(limit))],
    }


def collect_services_status(limit=DEFAULT_LIMIT):
    if not _is_linux():
        return _unsupported()

    if not shutil.which("systemctl"):
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
            "reason": result.stderr.strip() or "systemctl misslyckades",
        }

    services = []

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line:
            continue

        parts = line.split(None, 4)
        services.append(
            {
                "unit": parts[0],
                "load": parts[1] if len(parts) > 1 else "",
                "active": parts[2] if len(parts) > 2 else "",
                "sub": parts[3] if len(parts) > 3 else "",
                "description": parts[4] if len(parts) > 4 else "",
            }
        )

    return {
        "supported": True,
        "available": True,
        "services": services[: max(1, int(limit))],
    }


def collect_system_logs(limit=DEFAULT_LIMIT):
    if not _is_linux():
        return _unsupported()

    if not shutil.which("journalctl"):
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
            str(max(1, int(limit))),
            "--no-pager",
            "--output=short-iso",
        ]
    )

    if result.returncode != 0:
        return {
            "supported": True,
            "available": False,
            "entries": [],
            "reason": result.stderr.strip() or "journalctl misslyckades",
        }

    entries = [
        line.strip()
        for line in result.stdout.splitlines()
        if line.strip() and not line.startswith("-- ")
    ]

    return {
        "supported": True,
        "available": True,
        "entries": entries[-max(1, int(limit)):],
    }


def format_network_status(result):
    if not result.get("supported"):
        return (
            "Pi-nätverksstatus kräver Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    lines = ["Raspberry Pi/Linux nätverksgränssnitt:"]

    for interface in result.get("interfaces", []):
        state = "up" if interface.get("up") else "down"
        addresses = ", ".join(
            f"{item['type']}={item['address']}"
            for item in interface.get("addresses", [])
        ) or "ingen IP-adress"
        speed = interface.get("speed_mbps")
        speed_text = f", {speed} Mbit/s" if speed else ""
        lines.append(
            f"- {interface['name']}: {state}{speed_text}, {addresses}"
        )

    if len(lines) == 1:
        lines.append("- Inga nätverksgränssnitt hittades.")

    return "\n".join(lines)


def format_process_status(result):
    if not result.get("supported"):
        return (
            "Pi-processlista kräver Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    lines = ["Processer med högst minnesanvändning:"]

    for item in result.get("processes", []):
        lines.append(
            f"- PID {item.get('pid')}: {item.get('name') or 'okänd'} | "
            f"CPU {item.get('cpu_percent', 0):.1f}% | "
            f"RAM {item.get('memory_percent', 0):.1f}%"
        )

    if len(lines) == 1:
        lines.append("- Inga processer kunde läsas.")

    return "\n".join(lines)


def format_services_status(result):
    if not result.get("supported"):
        return (
            "Pi-tjänststatus kräver Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    if not result.get("available", False):
        return "Tjänststatus kunde inte läsas: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = ["Körande systemd-tjänster:"]

    for service in result.get("services", []):
        description = service.get("description") or ""
        suffix = f" - {description}" if description else ""
        lines.append(f"- {service.get('unit')}{suffix}")

    if len(lines) == 1:
        lines.append("- Inga körande tjänster rapporterades.")

    return "\n".join(lines)


def format_system_logs(result):
    if not result.get("supported"):
        return (
            "Pi-systemloggar kräver Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    if not result.get("available", False):
        return "Systemloggar kunde inte läsas: " + result.get(
            "reason",
            "okänd orsak",
        )

    lines = ["Senaste journalposter på warning-nivå eller högre:"]
    lines.extend(f"- {entry}" for entry in result.get("entries", []))

    if len(lines) == 1:
        lines.append("- Inga sådana loggposter hittades.")

    return "\n".join(lines)


def pi_network_status():
    try:
        return format_network_status(collect_network_status())
    except Exception as error:
        return f"Fel vid nätverksstatus: {error}"


def pi_process_status():
    try:
        return format_process_status(collect_process_status())
    except Exception as error:
        return f"Fel vid processstatus: {error}"


def pi_services_status():
    try:
        return format_services_status(collect_services_status())
    except Exception as error:
        return f"Fel vid tjänststatus: {error}"


def pi_system_logs():
    try:
        return format_system_logs(collect_system_logs())
    except Exception as error:
        return f"Fel vid systemloggar: {error}"


TOOLS = {
    "pi_network_status": {
        "function": pi_network_status,
        "description": (
            "Visar read-only nätverksgränssnitt, IP-adresser och länkstatus "
            "på Linux/Raspberry Pi."
        ),
    },
    "pi_process_status": {
        "function": pi_process_status,
        "description": (
            "Visar read-only processöversikt med CPU- och RAM-användning "
            "på Linux/Raspberry Pi."
        ),
    },
    "pi_services_status": {
        "function": pi_services_status,
        "description": (
            "Visar read-only körande systemd-tjänster på Linux/Raspberry Pi."
        ),
    },
    "pi_system_logs": {
        "function": pi_system_logs,
        "description": (
            "Visar read-only senaste systemd-journalposter på warning-nivå "
            "eller högre på Linux/Raspberry Pi."
        ),
    },
}
