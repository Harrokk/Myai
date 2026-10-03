from core.config import load_settings


def verify_nmea_checksum(sentence):
    text = (sentence or "").strip()

    if not text.startswith("$") or "*" not in text:
        return False

    body, checksum_text = text[1:].rsplit("*", 1)

    if len(checksum_text) < 2:
        return False

    checksum = 0

    for char in body:
        checksum ^= ord(char)

    try:
        expected = int(checksum_text[:2], 16)
    except ValueError:
        return False

    return checksum == expected


def _coordinate_to_decimal(value, hemisphere):
    if not value or not hemisphere:
        raise ValueError("Koordinat saknas.")

    hemisphere = hemisphere.upper()
    degree_digits = 2 if hemisphere in {"N", "S"} else 3

    if hemisphere not in {"N", "S", "E", "W"}:
        raise ValueError("Ogiltig hemisfär.")

    degrees = int(value[:degree_digits])
    minutes = float(value[degree_digits:])
    decimal = degrees + minutes / 60.0

    if hemisphere in {"S", "W"}:
        decimal = -decimal

    return round(decimal, 7)


def parse_nmea_sentence(sentence):
    text = (sentence or "").strip()

    if not verify_nmea_checksum(text):
        raise ValueError("NMEA-checksumman är ogiltig.")

    body = text[1:text.rfind("*")]
    fields = body.split(",")
    sentence_type = fields[0][-3:]

    if sentence_type == "RMC":
        if len(fields) < 10 or fields[2] != "A":
            return None

        return {
            "source": "RMC",
            "latitude": _coordinate_to_decimal(fields[3], fields[4]),
            "longitude": _coordinate_to_decimal(fields[5], fields[6]),
            "utc_time": fields[1] or None,
            "date": fields[9] or None,
            "speed_knots": float(fields[7]) if fields[7] else None,
            "course_degrees": float(fields[8]) if fields[8] else None,
        }

    if sentence_type == "GGA":
        if len(fields) < 10:
            return None

        try:
            fix_quality = int(fields[6] or "0")
        except ValueError:
            fix_quality = 0

        if fix_quality <= 0:
            return None

        return {
            "source": "GGA",
            "latitude": _coordinate_to_decimal(fields[2], fields[3]),
            "longitude": _coordinate_to_decimal(fields[4], fields[5]),
            "utc_time": fields[1] or None,
            "fix_quality": fix_quality,
            "satellites": int(fields[7]) if fields[7].isdigit() else None,
            "hdop": float(fields[8]) if fields[8] else None,
            "altitude_m": float(fields[9]) if fields[9] else None,
        }

    return None


def _load_serial():
    try:
        import serial
    except ImportError as error:
        raise RuntimeError(
            "GPS-läsning kräver pyserial. "
            "Installera requirements-gps.txt."
        ) from error

    return serial


def read_gps_fix(settings=None, serial_module=None):
    settings = settings or load_settings()
    config = settings.get("gps", {})

    if not config.get("enabled", False):
        return {
            "available": False,
            "reason": "GPS är avstängt i konfigurationen.",
        }

    port = (config.get("port") or "").strip()

    if not port:
        return {
            "available": False,
            "reason": "Ingen GPS-port är konfigurerad.",
        }

    serial = serial_module or _load_serial()
    baudrate = int(config.get("baudrate", 9600))
    timeout = float(config.get("timeout_seconds", 2))
    max_lines = max(1, int(config.get("max_lines", 20)))

    connection = serial.Serial(
        port=port,
        baudrate=baudrate,
        timeout=timeout,
    )

    try:
        for _ in range(max_lines):
            raw = connection.readline()

            if isinstance(raw, bytes):
                line = raw.decode("ascii", errors="ignore")
            else:
                line = str(raw)

            if not line.strip():
                continue

            try:
                fix = parse_nmea_sentence(line)
            except ValueError:
                continue

            if fix is not None:
                return {
                    "available": True,
                    "port": port,
                    "fix": fix,
                }

        return {
            "available": False,
            "reason": (
                "Ingen giltig GPS-fix hittades inom det konfigurerade "
                "antalet NMEA-rader."
            ),
            "port": port,
        }
    finally:
        connection.close()


def format_gps_status(result):
    if not result.get("available"):
        return "GPS-position kunde inte läsas: " + result.get(
            "reason",
            "okänd orsak",
        )

    fix = result["fix"]
    lines = [
        f"GPS-position: {fix['latitude']:.7f}, {fix['longitude']:.7f}",
        f"Källa: {fix.get('source')}",
    ]

    if fix.get("altitude_m") is not None:
        lines.append(f"Höjd: {fix['altitude_m']:.1f} m")

    if fix.get("satellites") is not None:
        lines.append(f"Satelliter: {fix['satellites']}")

    if fix.get("speed_knots") is not None:
        lines.append(f"Hastighet: {fix['speed_knots']:.1f} knop")

    if fix.get("utc_time"):
        lines.append(f"GPS-tid (UTC): {fix['utc_time']}")

    return "\n".join(lines)


def gps_status():
    try:
        return format_gps_status(read_gps_fix())
    except Exception as error:
        return f"GPS-position kunde inte läsas: {error}"


TOOLS = {
    "gps_status": {
        "function": gps_status,
        "description": (
            "Läser en checksummeverifierad GPS-position från en konfigurerad "
            "seriell NMEA-mottagare."
        ),
    }
}
