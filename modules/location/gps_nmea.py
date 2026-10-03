import json
import time
from datetime import datetime, timezone
from pathlib import Path

from core.config import PROJECT_ROOT, load_settings
from modules.location.location import normalize_location_fix


def _load_serial():
    try:
        import serial
    except ImportError as error:
        raise RuntimeError(
            "GPS via seriell port kräver pyserial. "
            "Installera requirements-gps.txt."
        ) from error

    return serial


def nmea_checksum(body):
    value = 0

    for character in body:
        value ^= ord(character)

    return value


def validate_nmea_checksum(sentence):
    text = (sentence or "").strip()

    if not text.startswith("$") or "*" not in text:
        return False

    body, checksum_text = text[1:].rsplit("*", 1)

    if len(checksum_text) < 2:
        return False

    try:
        expected = int(checksum_text[:2], 16)
    except ValueError:
        return False

    return nmea_checksum(body) == expected


def _coordinate(value, hemisphere, degree_digits):
    if not value:
        raise ValueError("NMEA-koordinat saknas.")

    if hemisphere not in {"N", "S", "E", "W"}:
        raise ValueError("NMEA-väderstreck är ogiltigt.")

    if len(value) <= degree_digits:
        raise ValueError("NMEA-koordinat har ogiltigt format.")

    try:
        degrees = float(value[:degree_digits])
        minutes = float(value[degree_digits:])
    except ValueError as error:
        raise ValueError("NMEA-koordinat är inte numerisk.") from error

    if not 0 <= minutes < 60:
        raise ValueError("NMEA-minuter måste ligga mellan 0 och 60.")

    decimal = degrees + minutes / 60.0

    if hemisphere in {"S", "W"}:
        decimal *= -1

    return decimal


def _rmc_timestamp(time_text, date_text):
    if not time_text or not date_text:
        raise ValueError("RMC saknar datum eller UTC-tid.")

    formats = (
        "%d%m%y%H%M%S.%f",
        "%d%m%y%H%M%S",
    )
    combined = date_text + time_text

    for fmt in formats:
        try:
            parsed = datetime.strptime(combined, fmt)
            return parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue

    raise ValueError("RMC datum/tid kunde inte tolkas.")


def parse_rmc(sentence):
    text = (sentence or "").strip()

    if not validate_nmea_checksum(text):
        raise ValueError("NMEA-checksumman är ogiltig.")

    body = text[1:text.rfind("*")]
    fields = body.split(",")

    if not fields or not fields[0].endswith("RMC"):
        raise ValueError("NMEA-raden är inte en RMC-fix.")

    if len(fields) < 10:
        raise ValueError("RMC-raden saknar obligatoriska fält.")

    time_text = fields[1]
    status = fields[2].upper()
    latitude_text = fields[3]
    latitude_hemi = fields[4].upper()
    longitude_text = fields[5]
    longitude_hemi = fields[6].upper()
    date_text = fields[9]

    if status != "A":
        raise ValueError("RMC rapporterar ingen aktiv GPS-fix.")

    latitude = _coordinate(
        latitude_text,
        latitude_hemi,
        2,
    )
    longitude = _coordinate(
        longitude_text,
        longitude_hemi,
        3,
    )
    timestamp = _rmc_timestamp(time_text, date_text)

    return normalize_location_fix(
        {
            "latitude": latitude,
            "longitude": longitude,
            "source": "gps",
            "accuracy_m": None,
            "altitude_m": None,
            "timestamp": timestamp,
        }
    )


def read_gps_fix(
    port,
    baudrate=9600,
    timeout_seconds=10,
    serial_module=None,
):
    if not str(port or "").strip():
        raise ValueError("GPS-port är inte konfigurerad.")

    try:
        baudrate = int(baudrate)
        timeout_seconds = float(timeout_seconds)
    except (TypeError, ValueError) as error:
        raise ValueError(
            "GPS baudrate/timeout måste vara numeriska."
        ) from error

    if baudrate <= 0:
        raise ValueError("GPS baudrate måste vara större än 0.")

    if timeout_seconds <= 0:
        raise ValueError("GPS timeout måste vara större än 0.")

    serial = serial_module or _load_serial()
    handle = serial.Serial(
        str(port),
        baudrate=baudrate,
        timeout=min(1.0, timeout_seconds),
    )
    deadline = time.monotonic() + timeout_seconds

    try:
        while time.monotonic() < deadline:
            raw = handle.readline()

            if not raw:
                continue

            if isinstance(raw, bytes):
                line = raw.decode("ascii", errors="ignore").strip()
            else:
                line = str(raw).strip()

            if "RMC" not in line:
                continue

            try:
                return parse_rmc(line)
            except ValueError:
                continue

        return None
    finally:
        handle.close()


def save_location_fix(fix, path):
    normalized = normalize_location_fix(fix)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(normalized, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    temporary.replace(path)
    return normalized


def refresh_gps_location(
    settings=None,
    serial_module=None,
):
    settings = settings or load_settings()
    location_config = settings.get("location", {})
    gps_config = settings.get("gps", {})

    if not location_config.get("enabled", False):
        return "Position är avstängd i konfigurationen."

    if not gps_config.get("enabled", False):
        return "GPS-provider är avstängd i konfigurationen."

    port = (gps_config.get("port") or "").strip()

    if not port:
        return "Ingen GPS-port är konfigurerad."

    fix = read_gps_fix(
        port=port,
        baudrate=gps_config.get("baudrate", 9600),
        timeout_seconds=gps_config.get("timeout_seconds", 10),
        serial_module=serial_module,
    )

    if fix is None:
        return (
            "Ingen giltig aktiv RMC-position mottogs inom GPS-timeout."
        )

    path = PROJECT_ROOT / location_config.get(
        "file",
        "runtime/location.json",
    )
    save_location_fix(fix, path)

    return (
        "GPS-position uppdaterad: "
        f"{fix['latitude']:.6f}, {fix['longitude']:.6f} "
        f"({fix['timestamp']})."
    )


def gps_refresh_location():
    try:
        return refresh_gps_location()
    except Exception as error:
        return f"GPS-uppdateringen misslyckades: {error}"


TOOLS = {
    "gps_refresh_location": {
        "function": gps_refresh_location,
        "description": (
            "Läser en aktiv NMEA-RMC GPS-fix från den konfigurerade "
            "seriella porten och sparar den i MyAI:s normaliserade "
            "positionsformat."
        ),
    }
}
