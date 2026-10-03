from core.config import load_settings


def nmea_checksum(sentence):
    text = sentence.strip()

    if text.startswith("$"):
        text = text[1:]

    if "*" in text:
        text = text.split("*", 1)[0]

    checksum = 0

    for char in text:
        checksum ^= ord(char)

    return checksum


def validate_nmea_checksum(sentence):
    text = sentence.strip()

    if not text.startswith("$") or "*" not in text:
        return False

    body, supplied = text[1:].rsplit("*", 1)

    if len(supplied) < 2:
        return False

    try:
        expected = int(supplied[:2], 16)
    except ValueError:
        return False

    calculated = 0

    for char in body:
        calculated ^= ord(char)

    return calculated == expected


def _coordinate_to_decimal(raw_value, hemisphere):
    if not raw_value or not hemisphere:
        return None

    hemisphere = hemisphere.upper()

    if hemisphere not in {"N", "S", "E", "W"}:
        raise ValueError(f"Ogiltig NMEA-riktning: {hemisphere}")

    degree_digits = 2 if hemisphere in {"N", "S"} else 3

    if len(raw_value) <= degree_digits:
        raise ValueError("Ogiltigt NMEA-koordinatformat.")

    degrees = int(raw_value[:degree_digits])
    minutes = float(raw_value[degree_digits:])
    decimal = degrees + minutes / 60.0

    if hemisphere in {"S", "W"}:
        decimal = -decimal

    return round(decimal, 8)


def parse_nmea_sentence(sentence, require_checksum=True):
    text = sentence.strip()

    if not text:
        return None

    if require_checksum and not validate_nmea_checksum(text):
        raise ValueError("NMEA-checksumman är ogiltig.")

    body = text[1:] if text.startswith("$") else text

    if "*" in body:
        body = body.split("*", 1)[0]

    fields = body.split(",")

    if not fields or len(fields[0]) < 3:
        return None

    sentence_type = fields[0][-3:].upper()

    if sentence_type == "GGA":
        if len(fields) < 10:
            raise ValueError("GGA-meningen saknar obligatoriska fält.")

        fix_quality = int(fields[6] or 0)
        valid = fix_quality > 0

        return {
            "sentence_type": "GGA",
            "valid": valid,
            "utc_time": fields[1] or None,
            "latitude": (
                _coordinate_to_decimal(fields[2], fields[3])
                if fields[2] and fields[3]
                else None
            ),
            "longitude": (
                _coordinate_to_decimal(fields[4], fields[5])
                if fields[4] and fields[5]
                else None
            ),
            "fix_quality": fix_quality,
            "satellites": int(fields[7] or 0),
            "hdop": float(fields[8]) if fields[8] else None,
            "altitude_m": float(fields[9]) if fields[9] else None,
        }

    if sentence_type == "RMC":
        if len(fields) < 10:
            raise ValueError("RMC-meningen saknar obligatoriska fält.")

        valid = (fields[2] or "").upper() == "A"

        return {
            "sentence_type": "RMC",
            "valid": valid,
            "utc_time": fields[1] or None,
            "latitude": (
                _coordinate_to_decimal(fields[3], fields[4])
                if fields[3] and fields[4]
                else None
            ),
            "longitude": (
                _coordinate_to_decimal(fields[5], fields[6])
                if fields[5] and fields[6]
                else None
            ),
            "speed_knots": float(fields[7]) if fields[7] else None,
            "course_deg": float(fields[8]) if fields[8] else None,
            "date_ddmmyy": fields[9] or None,
        }

    return None


def merge_nmea_fixes(fixes):
    merged = {
        "latitude": None,
        "longitude": None,
        "utc_time": None,
        "date_ddmmyy": None,
        "fix_quality": None,
        "satellites": None,
        "hdop": None,
        "altitude_m": None,
        "speed_knots": None,
        "course_deg": None,
    }

    valid_count = 0

    for fix in fixes:
        if not fix or not fix.get("valid"):
            continue

        if fix.get("latitude") is None or fix.get("longitude") is None:
            continue

        valid_count += 1

        for key in merged:
            value = fix.get(key)

            if value is not None:
                merged[key] = value

    if valid_count == 0:
        return None

    merged["valid_sentences"] = valid_count
    return merged


def _load_serial():
    try:
        import serial
    except ImportError as error:
        raise RuntimeError(
            "GPS via seriell port kräver pyserial. "
            "Installera requirements-gps.txt."
        ) from error

    return serial


def read_gps_location(settings=None, serial_module=None):
    settings = settings or load_settings()
    location = settings.get("location", {})

    if not location.get("enabled", False):
        return {
            "success": False,
            "disabled": True,
            "fix": None,
            "error": "GPS/position är avstängd i konfigurationen.",
        }

    source = (location.get("source") or "gps_serial").strip().lower()

    if source != "gps_serial":
        return {
            "success": False,
            "disabled": False,
            "fix": None,
            "error": f"Positionskällan stöds inte ännu: {source}",
        }

    port_name = (location.get("serial_port") or "").strip()

    if not port_name:
        return {
            "success": False,
            "disabled": False,
            "fix": None,
            "error": "Ingen seriell GPS-port är konfigurerad.",
        }

    try:
        baudrate = int(location.get("baudrate", 9600))
        timeout = float(location.get("timeout_seconds", 1))
        max_lines = int(location.get("max_lines", 20))
    except (TypeError, ValueError) as error:
        raise ValueError("GPS-inställningarna måste vara numeriska.") from error

    if baudrate <= 0:
        raise ValueError("GPS baudrate måste vara större än 0.")

    if timeout <= 0:
        raise ValueError("GPS timeout_seconds måste vara större än 0.")

    if max_lines <= 0 or max_lines > 500:
        raise ValueError("GPS max_lines måste vara mellan 1 och 500.")

    serial_api = serial_module or _load_serial()
    connection = serial_api.Serial(
        port=port_name,
        baudrate=baudrate,
        timeout=timeout,
    )
    fixes = []
    invalid_lines = 0

    try:
        for _ in range(max_lines):
            raw = connection.readline()

            if not raw:
                continue

            if isinstance(raw, bytes):
                sentence = raw.decode("ascii", errors="ignore").strip()
            else:
                sentence = str(raw).strip()

            if not sentence:
                continue

            try:
                fix = parse_nmea_sentence(
                    sentence,
                    require_checksum=True,
                )
            except (ValueError, TypeError):
                invalid_lines += 1
                continue

            if fix is not None:
                fixes.append(fix)
    finally:
        connection.close()

    merged = merge_nmea_fixes(fixes)

    if merged is None:
        return {
            "success": False,
            "disabled": False,
            "fix": None,
            "invalid_lines": invalid_lines,
            "error": "Ingen giltig GPS-fix hittades i mottagna NMEA-data.",
        }

    return {
        "success": True,
        "disabled": False,
        "fix": merged,
        "invalid_lines": invalid_lines,
        "error": None,
    }


def format_gps_location(result):
    if result.get("disabled"):
        return (
            "GPS/position är avstängd. Aktivera location.enabled och "
            "konfigurera en seriell GPS-port."
        )

    if not result.get("success"):
        return (
            "GPS-position kunde inte läsas: "
            + (result.get("error") or "okänt fel")
        )

    fix = result["fix"]
    lines = [
        (
            f"GPS-position: {fix['latitude']:.6f}, "
            f"{fix['longitude']:.6f}"
        ),
        "Källa: seriell NMEA GPS-fix.",
    ]

    if fix.get("satellites") is not None:
        lines.append(f"Satelliter: {fix['satellites']}")

    if fix.get("hdop") is not None:
        lines.append(f"HDOP: {fix['hdop']}")

    if fix.get("altitude_m") is not None:
        lines.append(f"Höjd: {fix['altitude_m']:.1f} m")

    if fix.get("speed_knots") is not None:
        lines.append(f"Hastighet: {fix['speed_knots']:.2f} knop")

    lines.append(
        "Ingen noggrannhet i meter antas; faktisk precision beror på "
        "mottagare, satellitgeometri och miljö."
    )

    return "\n".join(lines)


def location_status():
    try:
        return format_gps_location(read_gps_location())
    except Exception as error:
        return f"GPS-position kunde inte läsas: {error}"


TOOLS = {
    "location_status": {
        "function": location_status,
        "description": (
            "Läser read-only aktuell position från en uttryckligen "
            "konfigurerad seriell NMEA-GPS utan att gissa position."
        ),
    }
}
