"""Skrivskyddad termisk telemetri för VENTUNO Q."""

from pathlib import Path


THERMAL_ROOT = Path("/sys/class/thermal")


def read_thermal_status(root=THERMAL_ROOT):
    temperatures = {}

    for zone in sorted(root.glob("thermal_zone*")):
        try:
            name = (zone / "type").read_text().strip()
            if not name.startswith("nsp-"):
                continue

            raw = int((zone / "temp").read_text().strip())
            temperatures[name] = raw / 1000.0
        except (OSError, ValueError):
            continue

    cooling_state = None
    cooling_max_state = None

    for device in sorted(root.glob("cooling_device*")):
        try:
            name = (device / "type").read_text().strip()
            if name != "cdsp:cdsp_sw":
                continue

            cooling_state = int(
                (device / "cur_state").read_text().strip()
            )
            cooling_max_state = int(
                (device / "max_state").read_text().strip()
            )
            break
        except (OSError, ValueError):
            continue

    return {
        "temperatures_c": temperatures,
        "min_c": min(temperatures.values()) if temperatures else None,
        "max_c": max(temperatures.values()) if temperatures else None,
        "avg_c": (
            sum(temperatures.values()) / len(temperatures)
            if temperatures else None
        ),
        "cooling_state": cooling_state,
        "cooling_max_state": cooling_max_state,
    }
