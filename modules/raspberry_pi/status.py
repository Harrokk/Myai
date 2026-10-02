from pathlib import Path
import platform
import subprocess

import psutil


MODEL_PATH = "/proc/device-tree/model"
THERMAL_PATH = "/sys/class/thermal/thermal_zone0/temp"

THROTTLED_FLAGS = {
    0: "underspänning pågår",
    1: "CPU-frekvensen är begränsad",
    2: "throttling pågår",
    3: "mjuk temperaturgräns är aktiv",
    16: "underspänning har inträffat",
    17: "CPU-frekvensbegränsning har inträffat",
    18: "throttling har inträffat",
    19: "mjuk temperaturgräns har inträffat",
}


def _read_text(path, reader=None):
    try:
        if reader is not None:
            value = reader(path)
        else:
            value = Path(path).read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        return None

    if value is None:
        return None

    return str(value).replace("\x00", "").strip() or None


def _run_vcgencmd(arguments, runner=None):
    command_runner = runner or subprocess.run

    try:
        completed = command_runner(
            ["vcgencmd", *arguments],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (FileNotFoundError, OSError, subprocess.SubprocessError):
        return None

    if completed.returncode != 0:
        return None

    return completed.stdout.strip() or None


def decode_throttled_flags(value):
    if value is None:
        return []

    if isinstance(value, str):
        text = value.strip().lower()
        if "=" in text:
            text = text.split("=", 1)[1].strip()
        numeric = int(text, 0)
    else:
        numeric = int(value)

    return [
        label
        for bit, label in THROTTLED_FLAGS.items()
        if numeric & (1 << bit)
    ]


def _temperature_c(reader=None, runner=None):
    raw = _read_text(THERMAL_PATH, reader=reader)

    if raw is not None:
        try:
            value = float(raw)
            if value > 1000:
                value /= 1000
            return round(value, 1)
        except ValueError:
            pass

    output = _run_vcgencmd(["measure_temp"], runner=runner)

    if not output or "=" not in output:
        return None

    value = output.split("=", 1)[1].replace("'C", "").strip()

    try:
        return round(float(value), 1)
    except ValueError:
        return None


def _core_voltage_v(runner=None):
    output = _run_vcgencmd(["measure_volts", "core"], runner=runner)

    if not output or "=" not in output:
        return None

    value = output.split("=", 1)[1].lower().replace("v", "").strip()

    try:
        return round(float(value), 3)
    except ValueError:
        return None


def _throttled_status(runner=None):
    output = _run_vcgencmd(["get_throttled"], runner=runner)

    if not output or "=" not in output:
        return {
            "raw": None,
            "flags": [],
        }

    raw = output.split("=", 1)[1].strip()

    try:
        flags = decode_throttled_flags(raw)
    except ValueError:
        flags = []

    return {
        "raw": raw,
        "flags": flags,
    }


def get_raspberry_pi_status(reader=None, runner=None, psutil_module=None):
    system = psutil_module or psutil
    model = _read_text(MODEL_PATH, reader=reader)
    is_pi = bool(model and "raspberry pi" in model.lower())

    cpu_percent = system.cpu_percent(interval=0.1)
    memory = system.virtual_memory()
    disk = system.disk_usage("/")
    throttled = _throttled_status(runner=runner)

    return {
        "is_raspberry_pi": is_pi,
        "model": model,
        "platform": platform.platform(),
        "cpu_percent": cpu_percent,
        "ram_used_gb": round(memory.used / (1024 ** 3), 2),
        "ram_total_gb": round(memory.total / (1024 ** 3), 2),
        "ram_percent": memory.percent,
        "disk_free_gb": round(disk.free / (1024 ** 3), 2),
        "disk_total_gb": round(disk.total / (1024 ** 3), 2),
        "disk_percent": disk.percent,
        "temperature_c": _temperature_c(reader=reader, runner=runner),
        "core_voltage_v": _core_voltage_v(runner=runner),
        "throttled_raw": throttled["raw"],
        "throttling_flags": throttled["flags"],
        "power_w": None,
    }


def format_raspberry_pi_status(status):
    if not status.get("is_raspberry_pi"):
        return (
            "Systemet identifierades inte som en Raspberry Pi. "
            "Pi-specifika värden kan därför inte verifieras här."
        )

    lines = [
        f"Raspberry Pi: {status.get('model') or 'modell okänd'}",
        f"CPU-belastning: {status['cpu_percent']}%",
        (
            "RAM: "
            f"{status['ram_used_gb']:.2f} GB / "
            f"{status['ram_total_gb']:.2f} GB "
            f"({status['ram_percent']}%)"
        ),
        (
            "Lagring /: "
            f"{status['disk_free_gb']:.2f} GB ledigt / "
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

    flags = status.get("throttling_flags") or []
    if status.get("throttled_raw") is None:
        lines.append("Throttling: kunde inte läsas")
    elif flags:
        lines.append("Throttling: " + "; ".join(flags))
    else:
        lines.append("Throttling: inga flaggor rapporterade")

    lines.append(
        "Total strömförbrukning: ej direkt mätbar utan extern mätkälla "
        "(t.ex. USB-C-effektmätare eller kompatibel strömsensor)."
    )

    return "\n".join(lines)


def raspberry_pi_status():
    try:
        return format_raspberry_pi_status(get_raspberry_pi_status())
    except Exception as error:
        return f"Raspberry Pi-status kunde inte läsas: {error}"


TOOLS = {
    "raspberry_pi_status": {
        "function": raspberry_pi_status,
        "description": (
            "Visar Raspberry Pi-systemstatus: CPU, RAM, lagring, temperatur, "
            "kärnspänning och throttling utan att gissa strömförbrukning."
        ),
    }
}
