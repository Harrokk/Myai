import json
from copy import deepcopy

from core.backend_recovery import (
    HealthAwareBackendPolicy,
)
from core.config import DEFAULT_SETTINGS
from core.resilient_llm import (
    ResilientLLMClient,
)


class FakeLLM:
    def __init__(
        self,
        model,
        answer,
    ):
        self.provider_name = "geniex"
        self.model = model
        self.url = "http://geniex"
        self.answer = answer
        self.calls = 0

    def chat(
        self,
        messages,
        timeout=300,
    ):
        self.calls += 1
        return self.answer


def write_watchdog(
    root,
    *,
    written,
    healthy,
    failures,
    successes,
):
    path = (
        root
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


def test_health_aware_recovery_full_cycle(tmp_path):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["fallback"][
        "health_aware"
    ].update(
        {
            "enabled": True,
            "failure_threshold": 3,
            "recovery_success_threshold": 3,
        }
    )
    settings["geniex_supervisor"][
        "state_path"
    ] = "runtime/geniex_health.json"
    settings["geniex_supervisor"][
        "state_stale_seconds"
    ] = 30

    now = [100.0]
    policy = HealthAwareBackendPolicy(
        settings,
        tmp_path,
        clock=lambda: now[0],
    )
    primary = FakeLLM(
        "primary",
        "primär",
    )
    fallback = FakeLLM(
        "fallback",
        "reserv",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
        backend_policy=policy,
    )

    write_watchdog(
        tmp_path,
        written=99.0,
        healthy=False,
        failures=3,
        successes=0,
    )

    assert client.chat([]) == "reserv"
    assert primary.calls == 0
    assert fallback.calls == 1
    assert client.status()[
        "active_backend"
    ] == "fallback"

    now[0] = 102.0
    write_watchdog(
        tmp_path,
        written=101.0,
        healthy=True,
        failures=0,
        successes=2,
    )

    assert client.chat([]) == "reserv"
    assert primary.calls == 0
    assert fallback.calls == 2

    now[0] = 104.0
    write_watchdog(
        tmp_path,
        written=103.0,
        healthy=True,
        failures=0,
        successes=3,
    )

    assert client.chat([]) == "primär"
    assert primary.calls == 1
    assert fallback.calls == 2
    status = client.status()
    assert status[
        "active_backend"
    ] == "primary"
    assert status[
        "routing_reason"
    ] == (
        "watchdog recovery threshold reached"
    )
