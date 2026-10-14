import json

from core.health_status import (
    build_health_status,
    classify_health,
    read_health_state,
    write_health_state,
)


def runtime(
    backend="primary",
    error=None,
):
    return {
        "active_backend": backend,
        "provider": "geniex",
        "model": "primary-model",
        "primary_provider": "geniex",
        "primary_model": "primary-model",
        "fallback_provider": "geniex",
        "fallback_model": "fallback-model",
        "last_error": error,
    }


def geniex_state(
    *,
    healthy=True,
    failures=0,
    written=100.0,
):
    return {
        "written_unix_time": written,
        "check": {
            "enabled": True,
            "healthy": healthy,
            "consecutive_failures": failures,
        },
        "restart": {
            "attempted": False,
            "success": False,
        },
    }


def test_health_is_healthy_with_primary_and_ready_geniex():
    result = classify_health(
        runtime(),
        geniex_state(),
        supervisor_expected=True,
        stale_after_seconds=30,
        now=110,
    )

    assert result["level"] == "healthy"
    assert result["fallback_active"] is False
    assert result["geniex_healthy"] is True
    assert result["geniex_state_stale"] is False


def test_health_is_degraded_when_fallback_is_active():
    result = classify_health(
        runtime(
            backend="fallback",
            error="npu-fel",
        ),
        geniex_state(
            healthy=False,
            failures=3,
        ),
        supervisor_expected=True,
        stale_after_seconds=30,
        now=110,
    )

    assert result["level"] == "degraded"
    assert result["fallback_active"] is True
    assert result["geniex_consecutive_failures"] == 3
    assert any(
        "reservbackend"
        in reason
        for reason in result["reasons"]
    )


def test_health_is_unhealthy_when_geniex_is_down_without_fallback():
    result = classify_health(
        runtime(),
        geniex_state(
            healthy=False,
            failures=3,
        ),
        supervisor_expected=True,
        stale_after_seconds=30,
        now=110,
    )

    assert result["level"] == "unhealthy"
    assert result["geniex_healthy"] is False


def test_health_is_unknown_when_watchdog_state_is_stale():
    result = classify_health(
        runtime(),
        geniex_state(
            written=10,
        ),
        supervisor_expected=True,
        stale_after_seconds=30,
        now=100,
    )

    assert result["level"] == "unknown"
    assert result["geniex_state_stale"] is True
    assert any(
        "för gammal"
        in reason
        for reason in result["reasons"]
    )


def test_build_health_status_keeps_runtime_and_supervisor_details():
    result = build_health_status(
        runtime(
            backend="fallback",
        ),
        geniex_state(
            healthy=False,
            failures=2,
        ),
        supervisor_expected=True,
        stale_after_seconds=30,
        now=110,
    )

    assert result["llm_runtime"]["active_backend"] == "fallback"
    assert result["geniex"]["check"]["consecutive_failures"] == 2


def test_health_state_write_is_atomic_and_readable(tmp_path):
    path = tmp_path / "health.json"

    saved = write_health_state(
        path,
        {
            "level": "healthy",
            "reasons": [
                "ok",
            ],
        },
    )

    loaded = read_health_state(
        path
    )

    assert loaded["level"] == "healthy"
    assert loaded["reasons"] == ["ok"]
    assert isinstance(
        loaded["written_unix_time"],
        float,
    )
    assert saved == loaded

    parsed = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )
    assert parsed["level"] == "healthy"


def test_nonfinite_or_future_watchdog_date_is_unknown():
    for written in (float("nan"), float("inf"), float("-inf"), 10000.0):
        report = classify_health(
            runtime(), geniex_state(written=written),
            supervisor_expected=True, stale_after_seconds=30, now=100,
        )
        assert report["level"] == "unknown"
        assert report["geniex_state_stale"] is True


def test_corrupt_watchdog_counters_cannot_crash_health_status():
    for value in ("bad", None, float("nan"), float("inf"), -5, True, [], {}):
        data = geniex_state()
        data["check"]["consecutive_failures"] = value
        report = classify_health(
            runtime(), data,
            supervisor_expected=True, stale_after_seconds=30, now=110,
        )
        assert report["level"] == "unknown", repr(value)
        assert report["geniex_state_stale"] is True, repr(value)


def test_missing_health_timestamp_is_unknown_when_expected():
    data = geniex_state()
    data.pop("written_unix_time")
    report = classify_health(
        runtime(), data,
        supervisor_expected=True, stale_after_seconds=30, now=110,
    )
    assert report["level"] == "unknown"
    assert report["geniex_state_stale"] is True


def test_corrupt_watchdog_check_is_unknown_when_expected():
    for invalid in (None, [], 12, "broken"):
        data = geniex_state()
        data["check"] = invalid
        report = classify_health(
            runtime(), data,
            supervisor_expected=True, stale_after_seconds=30, now=110,
        )
        assert report["level"] == "unknown", repr(invalid)
        assert report["geniex_state_stale"] is True
