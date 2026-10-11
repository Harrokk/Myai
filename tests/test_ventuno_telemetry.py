from modules.ventuno.telemetry import read_thermal_status


def write_value(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(value))


def test_reads_nsp_temperatures_and_cdsp_cooling(tmp_path):
    write_value(tmp_path / "thermal_zone0/type", "nsp-0-0-0-thermal")
    write_value(tmp_path / "thermal_zone0/temp", "35400")
    write_value(tmp_path / "thermal_zone1/type", "nsp-0-1-0-thermal")
    write_value(tmp_path / "thermal_zone1/temp", "36200")
    write_value(tmp_path / "thermal_zone2/type", "cpu-thermal")
    write_value(tmp_path / "thermal_zone2/temp", "65000")

    write_value(tmp_path / "cooling_device0/type", "cdsp:cdsp_sw")
    write_value(tmp_path / "cooling_device0/cur_state", "0")
    write_value(tmp_path / "cooling_device0/max_state", "4")

    result = read_thermal_status(tmp_path)

    assert len(result["temperatures_c"]) == 2
    assert result["min_c"] == 35.4
    assert result["max_c"] == 36.2
    assert abs(result["avg_c"] - 35.8) < 0.001
    assert result["cooling_state"] == 0
    assert result["cooling_max_state"] == 4


def test_missing_sensors_are_handled(tmp_path):
    result = read_thermal_status(tmp_path)

    assert result["temperatures_c"] == {}
    assert result["min_c"] is None
    assert result["max_c"] is None
    assert result["avg_c"] is None
    assert result["cooling_state"] is None
    assert result["cooling_max_state"] is None


def test_invalid_sensor_values_are_ignored(tmp_path):
    write_value(tmp_path / "thermal_zone0/type", "nsp-0-0-0-thermal")
    write_value(tmp_path / "thermal_zone0/temp", "invalid")

    result = read_thermal_status(tmp_path)

    assert result["temperatures_c"] == {}
