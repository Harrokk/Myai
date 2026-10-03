import json
from datetime import datetime, timezone
from pathlib import Path

from core.config import PROJECT_ROOT, load_settings


DEFAULT_LOCATION_PATH = PROJECT_ROOT / "runtime" / "location.json"
ALLOWED_SOURCES = {"gps", "network", "bluetooth", "manual"}


def _as_float(value, field):
    try:
        return float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{field} måste vara numeriskt.") from error


def _parse_timestamp(value):
    if value in (None, ""):
        return None

    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        text = value.strip().replace("Z", "+00:00")

        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as error:
            raise ValueError("timestamp måste vara giltig ISO-8601.") from error
    else:
        raise ValueError("timestamp måste vara ISO-8601 text.")

    if parsed.tzinfo is None:
        raise ValueError("timestamp måste innehålla tidszon.")

    return parsed.astimezone(timezone.utc)


def normalize_location_fix(data):
    if not isinstance(data, dict):
        raise ValueError("Positionsfix måste vara ett JSON-objekt.")

    latitude = _as_float(data.get("latitude"), "latitude")
    longitude = _as_float(data.get("longitude"), "longitude")

    if not -90 <= latitude <= 90:
        raise ValueError("latitude måste ligga mellan -90 och 90.")

    if not -180 <= longitude <= 180:
        raise ValueError("longitude måste ligga mellan -180 och 180.")

    source = str(data.get("source") or "").strip().lower()

    if source not in ALLOWED_SOURCES:
        raise ValueError(
            "source måste vara gps, network, bluetooth eller manual."
        )

    accuracy = data.get("accuracy_m")

    if accuracy is not None:
        accuracy = _as_float(accuracy, "accuracy_m")

        if accuracy < 0:
            raise ValueError("accuracy_m får inte vara negativt.")

    altitude = data.get("altitude_m")

    if altitude is not None:
        altitude = _as_float(altitude, "altitude_m")

    timestamp = _parse_timestamp(data.get("timestamp"))

    return {
        "latitude": latitude,
        "longitude": longitude,
        "source": source,
        "accuracy_m": accuracy,
        "altitude_m": altitude,
        "timestamp": (
            timestamp.isoformat()
            if timestamp is not None
            else None
        ),
    }


def load_location_fix(path=DEFAULT_LOCATION_PATH):
    path = Path(path)

    if not path.exists():
        return None

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Positionsfilen innehåller ogiltig JSON.") from error

    return normalize_location_fix(data)


def location_age_seconds(fix, now=None):
    timestamp = _parse_timestamp(fix.get("timestamp"))

    if timestamp is None:
        return None

    reference = now or datetime.now(timezone.utc)

    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=timezone.utc)
    else:
        reference = reference.astimezone(timezone.utc)

    return max(0.0, (reference - timestamp).total_seconds())


def source_description(source):
    descriptions = {
        "gps": "GPS-position",
        "network": "ungefärlig nätverksposition",
        "bluetooth": "ungefärlig Bluetooth-närhetsposition",
        "manual": "manuellt angiven position",
    }
    return descriptions.get(source, "okänd positionskälla")


def build_location_status(
    settings=None,
    path=None,
    now=None,
):
    settings = settings or load_settings()
    config = settings.get("location", {})

    if not config.get("enabled", False):
        return {
            "enabled": False,
            "available": False,
            "fix": None,
            "stale": None,
            "age_seconds": None,
            "reason": "Position är avstängd i konfigurationen.",
        }

    location_path = (
        Path(path)
        if path is not None
        else PROJECT_ROOT / config.get("file", "runtime/location.json")
    )

    fix = load_location_fix(location_path)

    if fix is None:
        return {
            "enabled": True,
            "available": False,
            "fix": None,
            "stale": None,
            "age_seconds": None,
            "reason": "Ingen lokal positionsfix finns ännu.",
        }

    age = location_age_seconds(fix, now=now)
    max_age = config.get("max_age_seconds", 300)

    try:
        max_age = float(max_age)
    except (TypeError, ValueError) as error:
        raise ValueError("location.max_age_seconds måste vara numeriskt.") from error

    if max_age < 0:
        raise ValueError("location.max_age_seconds får inte vara negativt.")

    stale = age is not None and age > max_age

    return {
        "enabled": True,
        "available": True,
        "fix": fix,
        "stale": stale,
        "age_seconds": age,
        "reason": None,
    }


def format_location_status(status):
    if not status.get("enabled"):
        return status.get("reason") or "Position är avstängd."

    if not status.get("available"):
        return status.get("reason") or "Ingen position är tillgänglig."

    fix = status["fix"]
    lines = [
        f"Positionskälla: {source_description(fix['source'])}.",
        f"Latitud: {fix['latitude']:.6f}",
        f"Longitud: {fix['longitude']:.6f}",
    ]

    if fix.get("accuracy_m") is not None:
        lines.append(
            f"Rapporterad noggrannhet: ±{fix['accuracy_m']:.1f} m."
        )

    if fix.get("altitude_m") is not None:
        lines.append(f"Höjd: {fix['altitude_m']:.1f} m.")

    age = status.get("age_seconds")

    if age is None:
        lines.append("Positionens ålder är okänd.")
    else:
        lines.append(f"Positionens ålder: {age:.0f} s.")

    if status.get("stale"):
        lines.append(
            "Varning: positionen är äldre än tillåten maxålder och "
            "ska inte behandlas som aktuell."
        )

    if fix["source"] in {"network", "bluetooth"}:
        lines.append(
            "Källan är ungefärlig och ska inte behandlas som exakt GPS."
        )

    return "\n".join(lines)


def location_status():
    try:
        return format_location_status(build_location_status())
    except Exception as error:
        return f"Fel vid positionsstatus: {error}"


TOOLS = {
    "location_status": {
        "function": location_status,
        "description": (
            "Läser den senaste lokala positionsfixen och redovisar källa, "
            "koordinater, noggrannhet och om positionen är för gammal."
        ),
    }
}
