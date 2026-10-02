import platform
from pathlib import Path
import re
import shutil
import subprocess

import psutil


MODEL_PATH = Path("/proc/device-tree/model")
TEMP_PATH = Path("/sys/class/thermal/thermal_zone0/temp")

THROTTLED_FLAGS = {
    0: "underspänning pågår",
    1: "CPU-frekvensen är begränsad",
    2: "systemet throttlar",
    3: "mjuk temperaturgräns är aktiv",
    16: "underspänning har inträffat",
    17: "CPU-frekvensbegränsning har inträffat",
    18: "throttling har inträffat",
    19: "mjuk temperaturgräns har inträffat",
}


def _read_text(path):
    return Path(path).read_text(encoding="utf-8").strip("\x00\n ")


def _run(command):
    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=8,
        check=False,
    )


def detect_raspberry_pi():
    try:
        model = _read_text(MODEL_PATH)
    except (OSError, UnicodeError):
        model = ""

    if "raspberry pi" in model.lower():
        return True, model

    machine = f"{platform.system()} {platform.machine()}".lower()
    return False, model or machine


def parse_throttled(value):
    text = (value or "").strip().lower()

    if "=" in text:
        text = text.split("=", 1)[1].strip()

    try:
        bits = int(text, 16)
    except (TypeError, ValueError):
        raise ValueError(f"Ogiltigt throttlingvärde: {value!r}")

    active = [
        message
        for bit, message in THROTTLED_FLAGS.items()
        if bits & (1 << bit)
    ]

    return {
        "raw": bits,
        "hex": f"0x{bits:x}",
        "flags": active,
        "ok": bits == 0,
    }


def read_cpu_temperature():
    try:
        raw = _read_text(TEMP_PATH)
        value = float(raw)
        if value > 1000:
            value /= 1000
        return round(value, 1)
    except (OSError, ValueError, UnicodeError):
        pass

    if shutil.which("vcgencmd"):
        result = _run(["vcgencmd", "measure_temp"])
        match = re.search(r"(-?\d+(?:\.\d+)?)", result.stdout)
        if result.returncode == 0 and match:
            return round(float(match.group(1)), 1)

    return None


def read_throttling():
    if not shutil.which("vcgencmd"):
        return None

    result = _run(["vcgencmd", "get_throttled"])

    if result.returncode != 0:
        return None

    try:
        return parse_throttled(result.stdout)
    except ValueError:
        return None


def read_core_voltage():
    if not shutil.which("vcgencmd"):
        return None

    result = _run(["vcgencmd", "measure_volts", "core"])

    if result.returncode != 0:
        return None

    match = re.search(r"(-?\d+(?:\.\d+)?)\s*V", result.stdout, re.IGNORECASE)
    return float(match.group(1)) if match else None


def collect_pi_status():
    is_pi, model = detect_raspberry_pi()

    if not is_pi:
        return {
            "is_raspberry_pi": False,
            "model": model,
        }

    memory = psutil.virtual_memory()
    disk = psutil.disk_usage("/")

    return {
        "is_raspberry_pi": True,
        "model": model,
        "cpu_percent": psutil.cpu_percent(interval=0.2),
        "cpu_count": psutil.cpu_count(logical=True),
        "ram_used_gb": round(memory.used / (1024 ** 3), 2),
        "ram_total_gb": round(memory.total / (1024 ** 3), 2),
        "ram_percent": memory.percent,
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "temperature_c": read_cpu_temperature(),
        "throttling": read_throttling(),
        "core_voltage_v": read_core_voltage(),
    }


def format_pi_status(status):
    if not status.get("is_raspberry_pi"):
        return (
            "Raspberry Pi upptäcktes inte på den här datorn. "
            f"Identifiering: {status.get('model') or 'okänd'}"
        )

    lines = [
        f"Raspberry Pi: {status.get('model') or 'okänd modell'}",
        (
            f"CPU-belastning: {status['cpu_percent']}% "
            f"({status.get('cpu_count')} logiska kärnor)"
        ),
        (
            f"RAM: {status['ram_used_gb']:.2f} / "
            f"{status['ram_total_gb']:.2f} GB "
            f"({status['ram_percent']}%)"
        ),
        (
            f"Lagring: {status['disk_free_gb']:.2f} GB ledigt av "
            f"{status['disk_total_gb']:.2f} GB "
            f"({status['disk_percent']}% använt)"
        ),
    ]

    temperature = status.get("temperature_c")
    lines.append(
        f"CPU-temperatur: {temperature:.1f} °C"
        if temperature is not None
        else "CPU-temperatur: kunde inte läsas"
    )

    voltage = status.get("core_voltage_v")
    lines.append(
        f"Kärnspänning: {voltage:.3f} V"
        if voltage is not None
        else "Kärnspänning: kunde inte läsas"
    )

    throttling = status.get("throttling")

    if throttling is None:
        lines.append("Throttling/underspänning: kunde inte läsas")
    elif throttling["ok"]:
        lines.append("Throttling/underspänning: inga flaggor")
    else:
        lines.append(
            "Throttling/underspänning: "
            + ", ".join(throttling["flags"])
            + f" ({throttling['hex']})"
        )

    return "\n".join(lines)


def pi_system_status():
    try:
        return format_pi_status(collect_pi_status())
    except Exception as error:
        return f"Fel vid Raspberry Pi-status: {error}"


TOOLS = {
    "pi_system_status": {
        "function": pi_system_status,
        "description": (
            "Visar Raspberry Pi-systemstatus med CPU, RAM, lagring, "
            "temperatur, spänning och throttling när informationen finns."
        ),
    }
}
