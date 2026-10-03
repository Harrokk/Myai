from datetime import datetime, timezone
import json

from modules.location import location


def enabled_settings(tmp_path, max_age=300):
    return {
        "location": {
            "enabled": True,
            "file": str(tmp_path / "location.json"),
            "max_age_seconds": max_age,
        }
    }


def write_fix(tmp_path, **overrides):
    data = {
        "latitude": 59.33,
        "longitude": 18.06,
        "source": "gps",
        "accuracy_m": 5,
        "altitude_m": 20,
        "timestamp": "2026-10-03T16:00:00+00:00",
    }
    data.update(overrides)
    path = tmp_path / "location.json"
    path.write_text(
        json.dumps(data),
        encoding="utf-8",
    )
    return path


def test_normalize_location_fix_validates_coordinates():
    try:
        location.normalize_location_fix(
            {
                "latitude": 100,
                "longitude": 18,
                "source": "gps",
            }
        )
    except ValueError as error:
        assert "latitude" in str(error)
    else:
        raise AssertionError("Invalid latitude should fail")


def test_normalize_location_fix_rejects_unknown_source():
    try:
        location.normalize_location_fix(
            {
                "latitude": 59,
                "longitude": 18,
                "source": "magic",
            }
        )
    except ValueError as error:
        assert "source" in str(error)
    else:
        raise AssertionError("Unknown source should fail")


def test_load_location_fix_reads_valid_json(tmp_path):
    path = write_fix(tmp_path)

    fix = location.load_location_fix(path)

    assert fix["latitude"] == 59.33
    assert fix["longitude"] == 18.06
    assert fix["source"] == "gps"
    assert fix["accuracy_m"] == 5.0


def test_location_status_disabled_by_default():
    status = location.build_location_status(
        settings={
            "location": {
                "enabled": False,
            }
        }
    )

    assert status["enabled"] is False
    assert status["available"] is False


def test_location_status_reports_missing_fix(tmp_path):
    status = location.build_location_status(
        settings=enabled_settings(tmp_path)
    )

    assert status["available"] is False
    assert "Ingen lokal positionsfix" in status["reason"]


def test_location_status_marks_stale_fix(tmp_path):
    path = write_fix(tmp_path)
    now = datetime(
        2026,
        10,
        3,
        16,
        10,
        0,
        tzinfo=timezone.utc,
    )

    status = location.build_location_status(
        settings=enabled_settings(tmp_path, max_age=300),
        path=path,
        now=now,
    )

    assert status["available"] is True
    assert status["stale"] is True
    assert status["age_seconds"] == 600


def test_location_status_keeps_fresh_fix(tmp_path):
    path = write_fix(tmp_path)
    now = datetime(
        2026,
        10,
        3,
        16,
        2,
        0,
        tzinfo=timezone.utc,
    )

    status = location.build_location_status(
        settings=enabled_settings(tmp_path, max_age=300),
        path=path,
        now=now,
    )

    assert status["stale"] is False
    assert status["age_seconds"] == 120


def test_format_network_location_warns_that_it_is_approximate():
    text = location.format_location_status(
        {
            "enabled": True,
            "available": True,
            "fix": {
                "latitude": 59.3,
                "longitude": 18.0,
                "source": "network",
                "accuracy_m": 1000,
                "altitude_m": None,
                "timestamp": None,
            },
            "stale": False,
            "age_seconds": None,
        }
    )

    assert "ungefärlig nätverksposition" in text
    assert "inte behandlas som exakt GPS" in text


def test_naive_timestamp_is_rejected():
    try:
        location.normalize_location_fix(
            {
                "latitude": 59,
                "longitude": 18,
                "source": "manual",
                "timestamp": "2026-10-03T18:00:00",
            }
        )
    except ValueError as error:
        assert "tidszon" in str(error)
    else:
        raise AssertionError("Naive timestamp should fail")
