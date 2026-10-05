import json
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from core.runtime_service import (
    MyAIRuntimeService,
)


class FakeAssistant:
    llm_provider = "geniex"
    model = "test-model"

    def __init__(self):
        self.initialize_calls = 0

    def initialize(self):
        self.initialize_calls += 1


class FakeComponent:
    def __init__(
        self,
        *,
        start_result=True,
    ):
        self.start_result = (
            start_result
        )
        self.is_running = False
        self.start_calls = 0
        self.stop_calls = 0

    def start(self):
        self.start_calls += 1

        if self.start_result:
            self.is_running = True

        return self.start_result

    def stop(
        self,
        *args,
        **kwargs,
    ):
        self.stop_calls += 1
        self.is_running = False
        return True


def settings():
    value = deepcopy(
        DEFAULT_SETTINGS
    )
    value["hardware_watch"][
        "enabled"
    ] = True
    value["trusted_terminals"][
        "enabled"
    ] = True
    value["voice"]["enabled"] = True
    value["voice"][
        "handsfree_enabled"
    ] = True
    value["runtime"].update(
        {
            "require_preflight": False,
            "heartbeat_interval_seconds": 1,
            "shutdown_timeout_seconds": 2,
        }
    )
    return value


def test_headless_runtime_starts_and_stops_components(
    tmp_path,
):
    assistant = FakeAssistant()
    hardware = FakeComponent()
    terminal = FakeComponent()
    voice = FakeComponent()
    service = MyAIRuntimeService(
        settings(),
        tmp_path,
        assistant=assistant,
        hardware_monitor=hardware,
        terminal_handoff=terminal,
        voice_runner=voice,
        voice_session=object(),
        clock=lambda: 10.0,
        wall_clock=lambda: 123.0,
    )

    assert service.start() is True
    assert assistant.initialize_calls == 1
    assert hardware.start_calls == 1
    assert terminal.start_calls == 1
    assert voice.start_calls == 1
    assert service.running is True

    status = service.status()
    assert status["hardware_monitor"] is True
    assert status["terminal_handoff"] is True
    assert status["voice_handsfree"] is True

    assert service.stop() is True
    assert hardware.stop_calls == 1
    assert terminal.stop_calls == 1
    assert voice.stop_calls == 1
    assert service.running is False


def test_headless_runtime_writes_heartbeat(
    tmp_path,
):
    value = settings()
    value["hardware_watch"][
        "enabled"
    ] = False
    value["trusted_terminals"][
        "enabled"
    ] = False
    value["voice"]["enabled"] = False

    service = MyAIRuntimeService(
        value,
        tmp_path,
        assistant=FakeAssistant(),
        clock=lambda: 20.0,
        wall_clock=lambda: 456.0,
    )

    service.start()

    path = (
        tmp_path
        / "runtime"
        / "myai_runtime.json"
    )
    saved = json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )

    assert saved["running"] is True
    assert saved["llm_provider"] == "geniex"
    assert saved["model"] == "test-model"
    assert "written_unix_time" in saved


def test_component_start_failure_is_reported_not_hidden(
    tmp_path,
):
    value = settings()
    value["trusted_terminals"][
        "enabled"
    ] = False
    value["voice"]["enabled"] = False
    hardware = FakeComponent(
        start_result=False
    )
    service = MyAIRuntimeService(
        value,
        tmp_path,
        assistant=FakeAssistant(),
        hardware_monitor=hardware,
    )

    service.start()

    status = service.status()
    assert (
        "hardware_monitor"
        in status[
            "component_errors"
        ]
    )


def test_runtime_start_is_idempotent(
    tmp_path,
):
    value = settings()
    value["hardware_watch"][
        "enabled"
    ] = False
    value["trusted_terminals"][
        "enabled"
    ] = False
    value["voice"]["enabled"] = False
    assistant = FakeAssistant()
    service = MyAIRuntimeService(
        value,
        tmp_path,
        assistant=assistant,
    )

    assert service.start() is True
    assert service.start() is False
    assert assistant.initialize_calls == 1
