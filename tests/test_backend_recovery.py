import json
from copy import deepcopy

from core.backend_recovery import HealthAwareBackendPolicy
from core.config import DEFAULT_SETTINGS


def settings(tmp_path):
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["llm"]["fallback"]["health_aware"].update(
        {
            "enabled": True,
            "failure_threshold": 3,
            "recovery_success_threshold": 3,
        }
    )
    value["geniex_supervisor"]["state_path"] = (
        "runtime/geniex_health.json"
    )
    value["geniex_supervisor"]["state_stale_seconds"] = 30
    return value


def write_state(
    tmp_path,
    *,
    written,
    healthy,
    failures,
    successes,
):
    path = (
        tmp_path
        / "runtime"
        / "geniex_health.json"
    )
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            {
                "written_unix_time": written,
                "check": {
                    "enabled": True,
                    "healthy": healthy,
                    "consecutive_failures": failures,
                    "consecutive_successes": successes,
                },
            }
        ),
        encoding="utf-8",
    )


def test_failure_threshold_routes_primary_to_fallback(tmp_path):
    write_state(
        tmp_path,
        written=95,
        healthy=False,
        failures=3,
        successes=0,
    )
    policy = HealthAwareBackendPolicy(
        settings(tmp_path),
        tmp_path,
        clock=lambda: 100.0,
    )

    assert policy.choose_backend(
        "primary"
    ) == "fallback"
    assert policy.fallback_activated_at == 100.0
    assert (
        policy.last_reason
        == "watchdog failure threshold reached"
    )


def test_fallback_waits_for_fresh_recovery_streak(tmp_path):
    value = settings(tmp_path)
    now = [100.0]
    write_state(
        tmp_path,
        written=95,
        healthy=False,
        failures=3,
        successes=0,
    )
    policy = HealthAwareBackendPolicy(
        value,
        tmp_path,
        clock=lambda: now[0],
    )

    assert policy.choose_backend(
        "primary"
    ) == "fallback"

    write_state(
        tmp_path,
        written=99,
        healthy=True,
        failures=0,
        successes=3,
    )

    assert policy.choose_backend(
        "fallback"
    ) == "fallback"

    now[0] = 102.0
    write_state(
        tmp_path,
        written=101,
        healthy=True,
        failures=0,
        successes=3,
    )

    assert policy.choose_backend(
        "fallback"
    ) == "primary"
    assert policy.fallback_activated_at is None
    assert (
        policy.last_reason
        == "watchdog recovery threshold reached"
    )


def test_fallback_waits_until_recovery_success_threshold(tmp_path):
    now = [100.0]
    write_state(
        tmp_path,
        written=95,
        healthy=False,
        failures=3,
        successes=0,
    )
    policy = HealthAwareBackendPolicy(
        settings(tmp_path),
        tmp_path,
        clock=lambda: now[0],
    )
    assert policy.choose_backend(
        "primary"
    ) == "fallback"

    now[0] = 102.0
    write_state(
        tmp_path,
        written=101,
        healthy=True,
        failures=0,
        successes=2,
    )

    assert policy.choose_backend(
        "fallback"
    ) == "fallback"


def test_stale_watchdog_never_forces_backend_switch(tmp_path):
    write_state(
        tmp_path,
        written=10,
        healthy=False,
        failures=9,
        successes=0,
    )
    policy = HealthAwareBackendPolicy(
        settings(tmp_path),
        tmp_path,
        clock=lambda: 100.0,
    )

    assert policy.choose_backend(
        "primary"
    ) == "primary"
    assert policy.choose_backend(
        "fallback"
    ) == "fallback"


def test_disabled_health_routing_retries_primary(tmp_path):
    value = settings(tmp_path)
    value["llm"]["fallback"]["health_aware"]["enabled"] = False
    policy = HealthAwareBackendPolicy(
        value,
        tmp_path,
        clock=lambda: 100.0,
    )

    assert policy.choose_backend(
        "fallback"
    ) == "primary"
