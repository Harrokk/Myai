from modules.location import gps


GGA = "$GPGGA,123519,4807.038,N,01131.000,E,1,08,0.9,545.4,M,46.9,M,,*47"
RMC = "$GPRMC,123519,A,4807.038,N,01131.000,E,022.4,084.4,230394,003.1,W*6A"


def test_validate_known_nmea_checksums():
    assert gps.validate_nmea_checksum(GGA) is True
    assert gps.validate_nmea_checksum(RMC) is True
    assert gps.validate_nmea_checksum(GGA[:-2] + "00") is False


def test_parse_gga_position_and_quality():
    result = gps.parse_nmea_sentence(GGA)

    assert result["valid"] is True
    assert abs(result["latitude"] - 48.1173) < 0.000001
    assert abs(result["longitude"] - 11.51666667) < 0.000001
    assert result["fix_quality"] == 1
    assert result["satellites"] == 8
    assert result["hdop"] == 0.9
    assert result["altitude_m"] == 545.4


def test_parse_rmc_speed_course_and_date():
    result = gps.parse_nmea_sentence(RMC)

    assert result["valid"] is True
    assert result["speed_knots"] == 22.4
    assert result["course_deg"] == 84.4
    assert result["date_ddmmyy"] == "230394"


def test_bad_checksum_is_rejected():
    try:
        gps.parse_nmea_sentence(GGA[:-2] + "00")
    except ValueError as error:
        assert "checksumman" in str(error)
    else:
        raise AssertionError("Bad checksum should fail")


def test_merge_gga_and_rmc_fixes():
    merged = gps.merge_nmea_fixes(
        [
            gps.parse_nmea_sentence(GGA),
            gps.parse_nmea_sentence(RMC),
        ]
    )

    assert merged["latitude"] == gps.parse_nmea_sentence(RMC)["latitude"]
    assert merged["altitude_m"] == 545.4
    assert merged["satellites"] == 8
    assert merged["speed_knots"] == 22.4
    assert merged["valid_sentences"] == 2


def test_location_disabled_does_not_open_serial():
    class BrokenSerial:
        def Serial(self, **kwargs):
            raise AssertionError("Serial should not open")

    result = gps.read_gps_location(
        settings={
            "location": {
                "enabled": False,
            }
        },
        serial_module=BrokenSerial(),
    )

    assert result["disabled"] is True


def test_serial_gps_reads_valid_fix_and_closes():
    class Connection:
        def __init__(self):
            self.lines = [
                b"garbage\r\n",
                (GGA + "\r\n").encode("ascii"),
                (RMC + "\r\n").encode("ascii"),
            ]
            self.closed = False

        def readline(self):
            if self.lines:
                return self.lines.pop(0)
            return b""

        def close(self):
            self.closed = True

    connection = Connection()

    class SerialModule:
        def Serial(self, **kwargs):
            assert kwargs["port"] == "COM7"
            assert kwargs["baudrate"] == 9600
            return connection

    result = gps.read_gps_location(
        settings={
            "location": {
                "enabled": True,
                "source": "gps_serial",
                "serial_port": "COM7",
                "baudrate": 9600,
                "timeout_seconds": 1,
                "max_lines": 5,
            }
        },
        serial_module=SerialModule(),
    )

    assert result["success"] is True
    assert result["fix"]["satellites"] == 8
    assert result["fix"]["speed_knots"] == 22.4
    assert connection.closed is True


def test_serial_gps_reports_no_fix_and_closes():
    class Connection:
        closed = False

        def readline(self):
            return b"$GPRMC,123519,V,,,,,,,230394,,,N*53\r\n"

        def close(self):
            self.closed = True

    connection = Connection()

    class SerialModule:
        def Serial(self, **kwargs):
            return connection

    result = gps.read_gps_location(
        settings={
            "location": {
                "enabled": True,
                "source": "gps_serial",
                "serial_port": "COM8",
                "baudrate": 9600,
                "timeout_seconds": 1,
                "max_lines": 2,
            }
        },
        serial_module=SerialModule(),
    )

    assert result["success"] is False
    assert "Ingen giltig GPS-fix" in result["error"]
    assert connection.closed is True


def test_format_location_does_not_claim_meter_accuracy():
    text = gps.format_gps_location(
        {
            "success": True,
            "disabled": False,
            "fix": {
                "latitude": 59.123456,
                "longitude": 18.123456,
                "satellites": 9,
                "hdop": 0.8,
                "altitude_m": 25.0,
                "speed_knots": 0.0,
            },
        }
    )

    assert "59.123456" in text
    assert "Satelliter: 9" in text
    assert "Ingen noggrannhet i meter antas" in text
