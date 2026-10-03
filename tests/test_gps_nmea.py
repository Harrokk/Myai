import json

from modules.location import gps_nmea


KNOWN_RMC = (
    "$GPRMC,123519,A,4807.038,N,01131.000,E,"
    "022.4,084.4,230394,003.1,W*6A"
)


def make_sentence(body):
    checksum = gps_nmea.nmea_checksum(body)
    return f"$" + body + f"*{checksum:02X}"


def test_known_nmea_checksum_is_valid():
    assert gps_nmea.validate_nmea_checksum(KNOWN_RMC) is True


def test_bad_nmea_checksum_is_rejected():
    bad = KNOWN_RMC[:-2] + "00"

    assert gps_nmea.validate_nmea_checksum(bad) is False


def test_parse_rmc_converts_coordinates_and_timestamp():
    fix = gps_nmea.parse_rmc(KNOWN_RMC)

    assert round(fix["latitude"], 6) == 48.1173
    assert round(fix["longitude"], 6) == 11.516667
    assert fix["source"] == "gps"
    assert fix["timestamp"] == "1994-03-23T12:35:19+00:00"


def test_parse_rmc_accepts_gn_talker():
    sentence = make_sentence(
        "GNRMC,120000.00,A,5930.000,N,01800.000,E,"
        "0.0,0.0,031026,,,A"
    )

    fix = gps_nmea.parse_rmc(sentence)

    assert fix["latitude"] == 59.5
    assert fix["longitude"] == 18.0
    assert fix["timestamp"] == "2026-10-03T12:00:00+00:00"


def test_parse_rmc_rejects_void_fix():
    sentence = make_sentence(
        "GPRMC,120000,V,5930.000,N,01800.000,E,"
        "0.0,0.0,031026,,,N"
    )

    try:
        gps_nmea.parse_rmc(sentence)
    except ValueError as error:
        assert "ingen aktiv GPS-fix" in str(error)
    else:
        raise AssertionError("Void RMC should fail")


class FakeSerialHandle:
    def __init__(self, lines):
        self.lines = list(lines)
        self.closed = False

    def readline(self):
        if not self.lines:
            return b""
        return self.lines.pop(0)

    def close(self):
        self.closed = True


class FakeSerialModule:
    def __init__(self, handle):
        self.handle = handle
        self.calls = []

    def Serial(self, port, baudrate, timeout):
        self.calls.append(
            {
                "port": port,
                "baudrate": baudrate,
                "timeout": timeout,
            }
        )
        return self.handle


def test_read_gps_fix_skips_non_rmc_and_returns_active_fix():
    handle = FakeSerialHandle(
        [
            b"$GPGGA,ignored*00\r\n",
            (KNOWN_RMC + "\r\n").encode("ascii"),
        ]
    )
    serial = FakeSerialModule(handle)

    fix = gps_nmea.read_gps_fix(
        port="COM5",
        baudrate=9600,
        timeout_seconds=2,
        serial_module=serial,
    )

    assert fix["source"] == "gps"
    assert serial.calls[0]["port"] == "COM5"
    assert handle.closed is True


def test_save_location_fix_writes_normalized_json(tmp_path):
    path = tmp_path / "location.json"
    fix = gps_nmea.parse_rmc(KNOWN_RMC)

    saved = gps_nmea.save_location_fix(fix, path)
    data = json.loads(path.read_text(encoding="utf-8"))

    assert saved["source"] == "gps"
    assert data["latitude"] == saved["latitude"]
    assert not (tmp_path / "location.json.tmp").exists()


def test_refresh_gps_location_respects_disabled_provider():
    text = gps_nmea.refresh_gps_location(
        settings={
            "location": {
                "enabled": True,
            },
            "gps": {
                "enabled": False,
            },
        }
    )

    assert "avstängd" in text


def test_refresh_gps_location_requires_port():
    text = gps_nmea.refresh_gps_location(
        settings={
            "location": {
                "enabled": True,
            },
            "gps": {
                "enabled": True,
                "port": "",
            },
        }
    )

    assert "Ingen GPS-port" in text
