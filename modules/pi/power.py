from pathlib import Path
import platform


HWMON_ROOT = Path("/sys/class/hwmon")

KINDS = {
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


def _read_text(path):
    return Path(path).read_text(encoding="utf-8").strip()


def _read_number(path):
    return float(_read_text(path))


def _label_for(input_path):
    stem = input_path.name[:-len("_input")]
    label_path = input_path.with_name(stem + "_label")

    try:
        return _read_text(label_path)
    except (OSError, UnicodeError):
        return stem


def collect_power_telemetry():
    if platform.system().lower() != "linux":
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

    for hwmon in sorted(HWMON_ROOT.glob("hwmon*")):
        try:
            source = _read_text(hwmon / "name")
        except (OSError, UnicodeError):
            source = hwmon.name

        for kind, config in KINDS.items():
            for input_path in sorted(hwmon.glob(config["pattern"])):
                try:
                    raw = _read_number(input_path)
                except (OSError, UnicodeError, ValueError):
                    continue

                measurements.append(
                    {
                        "kind": kind,
                        "source": source,
                        "label": _label_for(input_path),
                        "value": raw / config["scale"],
                        "unit": config["unit"],
                        "path": str(input_path),
                    }
                )

    return {
        "supported": True,
        "platform": platform.system(),
        "measurements": measurements,
    }


def format_power_telemetry(result):
    if not result.get("supported"):
        return (
            "Pi-strömtelemetri kräver Linux/Raspberry Pi. "
            f"Nuvarande plattform: {result.get('platform') or 'okänd'}."
        )

    measurements = result.get("measurements", [])

    if not measurements:
        return (
            "Ingen ström-, effekt- eller spänningstelemetri exponerades via "
            "Linux hwmon. MyAI gör därför ingen uppskattning."
        )

    lines = ["Raspberry Pi/Linux strömtelemetri:"]

    for item in measurements:
        value = item["value"]
        unit = item["unit"]
        lines.append(
            f"- {item['source']} / {item['label']}: "
            f"{value:.3f} {unit} ({item['kind']})"
        )

    lines.append(
        "Värdena kommer från operativsystemets hwmon-gränssnitt; "
        "MyAI uppskattar inte saknade mätvärden."
    )
    return "\n".join(lines)


def pi_power_status():
    try:
        return format_power_telemetry(collect_power_telemetry())
    except Exception as error:
        return f"Fel vid strömtelemetri: {error}"


TOOLS = {
    "pi_power_status": {
        "function": pi_power_status,
        "description": (
            "Läser read-only effekt, spänning och ström från Linux hwmon "
            "på Raspberry Pi när hårdvara och drivrutiner exponerar mätvärden."
        ),
    }
}
