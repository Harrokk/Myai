from copy import deepcopy
from types import SimpleNamespace

import pytest

from core.config import DEFAULT_SETTINGS
from core.geniex_supervisor import GenieXSupervisor


class FakeResponse:
    def __init__(
        self,
        payload=None,
        *,
        status_error=None,
    ):
        self.payload = (
            payload
            if payload is not None
            else {
                "object": "list",
                "data": [],
            }
        )
        self.status_error = status_error

    def raise_for_status(self):
        if self.status_error is not None:
            raise self.status_error

    def json(self):
        return self.payload


def settings():
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["geniex_supervisor"].update(
        {
            "enabled": True,
            "failure_threshold": 2,
            "restart_enabled": False,
            "restart_command": [],
            "restart_cooldown_seconds": 60,
            "max_restart_attempts": 2,
        }
    )
    return value


def test_disabled_supervisor_does_not_probe():
    value = settings()
    value["geniex_supervisor"]["enabled"] = False
    calls = []

    supervisor = GenieXSupervisor(
        value,
        request_get=lambda *args, **kwargs: calls.append(
            (args, kwargs)
        ),
    )

    result = supervisor.check()

    assert result["status"] == "disabled"
    assert result["healthy"] is None
    assert calls == []


def test_health_check_uses_openai_models_endpoint():
    seen = {}

    def fake_get(url, timeout):
        seen["url"] = url
        seen["timeout"] = timeout
        return FakeResponse(
            {
                "object": "list",
                "data": [
                    {
                        "id": "model-a",
                    }
                ],
            }
        )

    supervisor = GenieXSupervisor(
        settings(),
        request_get=fake_get,
    )

    result = supervisor.check()

    assert result["healthy"] is True
    assert result["model_count"] == 1
    assert seen["url"] == (
        "http://127.0.0.1:18181/v1/models"
    )
    assert seen["timeout"] == 3.0


def test_successful_check_resets_consecutive_failures():
    sequence = iter(
        [
            RuntimeError("down"),
            FakeResponse(),
        ]
    )

    def fake_get(url, timeout):
        value = next(sequence)

        if isinstance(
            value,
            Exception,
        ):
            raise value

        return value

    supervisor = GenieXSupervisor(
        settings(),
        request_get=fake_get,
    )

    first = supervisor.check()
    second = supervisor.check()

    assert first["healthy"] is False
    assert first["consecutive_failures"] == 1
    assert second["healthy"] is True
    assert second["consecutive_failures"] == 0


def test_restart_is_not_attempted_before_threshold():
    value = settings()
    calls = []

    supervisor = GenieXSupervisor(
        value,
        request_get=lambda *args, **kwargs: (
            (_ for _ in ()).throw(
                RuntimeError("down")
            )
        ),
        command_runner=lambda command, timeout: calls.append(
            (command, timeout)
        ),
    )

    result = supervisor.supervise_once()

    assert result["check"]["healthy"] is False
    assert result["restart"]["attempted"] is False
    assert calls == []


def test_restart_remains_disabled_even_after_threshold():
    value = settings()
    calls = []

    supervisor = GenieXSupervisor(
        value,
        request_get=lambda *args, **kwargs: (
            (_ for _ in ()).throw(
                RuntimeError("down")
            )
        ),
        command_runner=lambda command, timeout: calls.append(
            (command, timeout)
        ),
    )

    supervisor.supervise_once()
    result = supervisor.supervise_once()

    assert result["check"]["consecutive_failures"] == 2
    assert result["restart"]["attempted"] is False
    assert calls == []


def test_explicit_restart_uses_argument_list_without_shell():
    value = settings()
    value["geniex_supervisor"].update(
        {
            "restart_enabled": True,
            "restart_command": [
                "systemctl",
                "restart",
                "geniex.service",
            ],
        }
    )
    seen = {}

    def runner(command, timeout):
        seen["command"] = command
        seen["timeout"] = timeout
        return SimpleNamespace(
            returncode=0,
            stdout="ok",
            stderr="",
        )

    supervisor = GenieXSupervisor(
        value,
        command_runner=runner,
        clock=lambda: 100.0,
    )

    result = supervisor.restart()

    assert result["attempted"] is True
    assert result["success"] is True
    assert seen["command"] == [
        "systemctl",
        "restart",
        "geniex.service",
    ]
    assert seen["timeout"] == 30.0


def test_restart_rejects_shell_string_configuration():
    value = settings()
    value["geniex_supervisor"].update(
        {
            "restart_enabled": True,
            "restart_command": (
                "systemctl restart geniex.service"
            ),
        }
    )

    supervisor = GenieXSupervisor(
        value,
        clock=lambda: 100.0,
    )

    with pytest.raises(
        ValueError,
        match="lista",
    ):
        supervisor.restart()


def test_restart_respects_cooldown_and_max_attempts():
    value = settings()
    value["geniex_supervisor"].update(
        {
            "restart_enabled": True,
            "restart_command": [
                "systemctl",
                "restart",
                "geniex.service",
            ],
            "restart_cooldown_seconds": 60,
            "max_restart_attempts": 2,
        }
    )
    now = [100.0]

    supervisor = GenieXSupervisor(
        value,
        command_runner=lambda command, timeout: (
            SimpleNamespace(
                returncode=0,
                stdout="",
                stderr="",
            )
        ),
        clock=lambda: now[0],
    )

    assert supervisor.restart()["attempted"] is True
    assert supervisor.restart()["attempted"] is False

    now[0] = 161.0
    assert supervisor.restart()["attempted"] is True

    now[0] = 222.0
    assert supervisor.restart()["attempted"] is False
    assert supervisor.restart_attempts == 2



def test_supervisor_tracks_success_streak_for_recovery():
    sequence = iter(
        [
            FakeResponse(),
            FakeResponse(),
            RuntimeError("down"),
            FakeResponse(),
        ]
    )

    def fake_get(url, timeout):
        value = next(sequence)

        if isinstance(
            value,
            Exception,
        ):
            raise value

        return value

    supervisor = GenieXSupervisor(
        settings(),
        request_get=fake_get,
    )

    first = supervisor.check()
    second = supervisor.check()
    third = supervisor.check()
    fourth = supervisor.check()

    assert first["consecutive_successes"] == 1
    assert second["consecutive_successes"] == 2
    assert third["consecutive_successes"] == 0
    assert third["consecutive_failures"] == 1
    assert fourth["consecutive_successes"] == 1
    assert fourth["consecutive_failures"] == 0
