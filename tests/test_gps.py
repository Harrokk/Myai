from modules.location import gps


RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"
GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"


class FakeConnection:
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
    def __init__(self, connection):
        self.connection = connection
        self.kwargs = None

    def Serial(self, **kwargs):
        self.kwargs = kwargs
        return self.connection


def gps_settings(enabled=True, port="COM7"):
    return {
        "gps": {
            "enabled": enabled,
            "port": port,
            "baudrate": 9600,
            "timeout_seconds": 1,
            "max_lines": 5,
        }
    }


def test_verify_nmea_checksum():
    assert gps.verify_nmea_checksum(RMC) is True
    assert gps.verify_nmea_checksum(RMC[:-2] + "00") is False


def test_parse_rmc_position():
    result = gps.parse_nmea_sentence(RMC)

    assert result["source"] == "RMC"
    assert result["latitude"] == 48.1173
    assert result["longitude"] == 11.5166667
    assert result["speed_knots"] == 22.4


def test_parse_gga_position_and_altitude():
    result = gps.parse_nmea_sentence(GGA)

    assert result["source"] == "GGA"
    assert result["latitude"] == 48.1173
    assert result["longitude"] == 11.5166667
    assert result["altitude_m"] == 545.4
    assert result["satellites"] == 8


def test_south_and_west_coordinates():
    assert gps._coordinate_to_decimal("3450.000", "S") < 0
    assert gps._coordinate_to_decimal("05822.000", "W") < 0


def test_disabled_gps_does_not_open_serial():
    result = gps.read_gps_fix(
        settings=gps_settings(enabled=False),
        serial_module=object(),
    )

    assert result["available"] is False
    assert "avstängt" in result["reason"]


def test_missing_port_is_explicit():
    result = gps.read_gps_fix(
        settings=gps_settings(port=""),
        serial_module=object(),
    )

    assert result["available"] is False
    assert "port" in result["reason"].lower()


def test_serial_reader_skips_bad_line_and_returns_valid_fix():
    connection = FakeConnection(
        [
            b"$GPRMC,bad*00\r\n",
            (RMC + "\r\n").encode("ascii"),
        ]
    )
    serial = FakeSerialModule(connection)

    result = gps.read_gps_fix(
        settings=gps_settings(),
        serial_module=serial,
    )

    assert result["available"] is True
    assert result["fix"]["latitude"] == 48.1173
    assert connection.closed is True
    assert serial.kwargs["port"] == "COM7"


def test_serial_reader_closes_when_no_fix():
    connection = FakeConnection([b"garbage\r\n"])
    serial = FakeSerialModule(connection)

    result = gps.read_gps_fix(
        settings=gps_settings(),
        serial_module=serial,
    )

    assert result["available"] is False
    assert connection.closed is True


def test_formatter_reports_coordinates():
    text = gps.format_gps_status(
        {
            "available": True,
            "fix": {
                "source": "GGA",
                "latitude": 59.33,
                "longitude": 18.06,
                "altitude_m": 12.5,
                "satellites": 10,
                "utc_time": "050000",
            },
        }
    )

    assert "59.3300000" in text
    assert "18.0600000" in text
    assert "12.5 m" in text
