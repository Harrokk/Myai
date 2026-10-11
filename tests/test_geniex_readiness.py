from types import SimpleNamespace

import pytest

from core.geniex_readiness import wait_for_geniex


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def clock(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class FakeSupervisor:
    def __init__(self, results):
        self.results = iter(results)
        self.calls = 0

    def check(self):
        self.calls += 1
        return next(self.results)


def test_immediately_ready():
    clock = FakeClock()
    supervisor = FakeSupervisor([
        {"healthy": True, "status": "ready"}
    ])

    result = wait_for_geniex(
        {},
        clock=clock.clock,
        sleep=clock.sleep,
        supervisor=supervisor,
    )

    assert result["healthy"] is True
    assert supervisor.calls == 1
    assert clock.now == 0


def test_waits_until_ready():
    clock = FakeClock()
    supervisor = FakeSupervisor([
        {"healthy": False, "status": "unhealthy"},
        {"healthy": False, "status": "unhealthy"},
        {"healthy": True, "status": "ready"},
    ])

    result = wait_for_geniex(
        {},
        timeout_seconds=10,
        interval_seconds=2,
        clock=clock.clock,
        sleep=clock.sleep,
        supervisor=supervisor,
    )

    assert result["healthy"] is True
    assert supervisor.calls == 3
    assert clock.now == 4


def test_timeout_when_unavailable():
    clock = FakeClock()

    class UnavailableSupervisor:
        def check(self):
            return {
                "healthy": False,
                "status": "unhealthy",
                "error": "connection refused",
            }

    with pytest.raises(TimeoutError, match="10 sekunder"):
        wait_for_geniex(
            {},
            timeout_seconds=10,
            interval_seconds=2,
            clock=clock.clock,
            sleep=clock.sleep,
            supervisor=UnavailableSupervisor(),
        )

    assert clock.now == 10


def test_disabled_check_is_not_ready():
    clock = FakeClock()

    class DisabledSupervisor:
        def check(self):
            return {"healthy": None, "status": "disabled"}

    with pytest.raises(TimeoutError):
        wait_for_geniex(
            {},
            timeout_seconds=0,
            clock=clock.clock,
            sleep=clock.sleep,
            supervisor=DisabledSupervisor(),
        )
