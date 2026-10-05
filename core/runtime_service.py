from pathlib import Path
import threading
import time

from core.assistant import MyAICore
from core.config_validation import (
    require_valid_settings,
)
from core.hardware_monitor import (
    HardwareMonitor,
)
from core.health_status import (
    write_health_state,
)
from core.terminal_connector_factory import (
    build_terminal_handoff_monitor,
)
from core.voice_handsfree import (
    VoiceHandsfreeRunner,
)
from core.voice_session import (
    VoiceSession,
)


class MyAIRuntimeService:
    """Headless lifecycle manager for deployed MyAI runtimes."""

    def __init__(
        self,
        settings,
        project_root,
        *,
        assistant=None,
        hardware_monitor=None,
        terminal_handoff=None,
        voice_session=None,
        voice_runner=None,
        clock=None,
        wall_clock=None,
    ):
        self.settings = settings
        self.project_root = Path(
            project_root
        )
        self.runtime = settings.get(
            "runtime",
            {},
        )
        self.assistant = (
            assistant
            or MyAICore(
                settings,
                self.project_root,
            )
        )
        self.hardware_monitor = (
            hardware_monitor
        )
        self.terminal_handoff = (
            terminal_handoff
        )
        self.voice_session = (
            voice_session
        )
        self.voice_runner = (
            voice_runner
        )
        self.clock = (
            clock
            or time.monotonic
        )
        self.wall_clock = (
            wall_clock
            or time.time
        )
        self.started_at = None
        self.running = False
        self.stop_event = (
            threading.Event()
        )
        self.last_error = None
        self.component_errors = {}

    def _runtime_path(
        self,
        key,
        default,
    ):
        raw = self.runtime.get(
            key,
            default,
        )
        path = Path(
            raw
        )

        if not path.is_absolute():
            path = (
                self.project_root
                / path
            )

        return path

    @property
    def heartbeat_path(self):
        return self._runtime_path(
            "heartbeat_path",
            "runtime/myai_runtime.json",
        )

    @property
    def heartbeat_interval_seconds(self):
        return max(
            1.0,
            float(
                self.runtime.get(
                    "heartbeat_interval_seconds",
                    10.0,
                )
            ),
        )

    def _record_component_error(
        self,
        name,
        error,
    ):
        value = (
            f"{type(error).__name__}: "
            f"{error}"
        )
        self.component_errors[
            name
        ] = value
        self.last_error = value

    def _build_hardware_monitor(self):
        if self.hardware_monitor is None:
            config = self.settings.get(
                "hardware_watch",
                {},
            )
            self.hardware_monitor = (
                HardwareMonitor(
                    interval_seconds=config.get(
                        "interval_seconds",
                        10,
                    ),
                    on_error=lambda error: (
                        self._record_component_error(
                            "hardware_monitor",
                            error,
                        )
                    ),
                )
            )

        return self.hardware_monitor

    def _build_terminal_handoff(self):
        if self.terminal_handoff is None:
            self.terminal_handoff = (
                build_terminal_handoff_monitor(
                    self.settings,
                    on_error=lambda error: (
                        self._record_component_error(
                            "terminal_handoff",
                            error,
                        )
                    ),
                )
            )

        return self.terminal_handoff

    def _build_voice(self):
        if self.voice_session is None:
            self.voice_session = (
                VoiceSession(
                    self.assistant,
                    settings=self.settings,
                )
            )

        if self.voice_runner is None:
            voice = self.settings.get(
                "voice",
                {},
            )
            self.voice_runner = (
                VoiceHandsfreeRunner(
                    self.voice_session,
                    on_error=lambda error: (
                        self._record_component_error(
                            "voice",
                            error,
                        )
                    ),
                    max_wait_frames=voice.get(
                        "handsfree_max_wait_frames",
                        voice.get(
                            "session_max_wait_frames",
                            1500,
                        ),
                    ),
                )
            )

        return self.voice_runner

    def start(self):
        if self.running:
            return False

        require_valid_settings(
            self.settings,
            require_ventuno_profile=bool(
                self.settings.get(
                    "ventuno",
                    {},
                ).get(
                    "enabled",
                    False,
                )
            ),
        )

        self.assistant.initialize()
        self.component_errors = {}
        self.last_error = None
        self.stop_event.clear()

        if self.settings.get(
            "hardware_watch",
            {},
        ).get(
            "enabled",
            False,
        ):
            try:
                started = (
                    self._build_hardware_monitor()
                    .start()
                )

                if started is False:
                    self.component_errors[
                        "hardware_monitor"
                    ] = (
                        "Hårdvarumonitor kunde inte starta."
                    )
            except Exception as error:
                self._record_component_error(
                    "hardware_monitor",
                    error,
                )

        if self.settings.get(
            "trusted_terminals",
            {},
        ).get(
            "enabled",
            False,
        ):
            try:
                started = (
                    self._build_terminal_handoff()
                    .start()
                )

                if started is False:
                    self.component_errors[
                        "terminal_handoff"
                    ] = (
                        "Terminalhandoff kunde inte starta."
                    )
            except Exception as error:
                self._record_component_error(
                    "terminal_handoff",
                    error,
                )

        voice = self.settings.get(
            "voice",
            {},
        )

        if (
            voice.get(
                "enabled",
                False,
            )
            and voice.get(
                "handsfree_enabled",
                False,
            )
        ):
            try:
                started = (
                    self._build_voice()
                    .start()
                )

                if started is False:
                    self.component_errors[
                        "voice"
                    ] = (
                        "Handsfree kunde inte starta."
                    )
            except Exception as error:
                self._record_component_error(
                    "voice",
                    error,
                )

        self.started_at = (
            self.clock()
        )
        self.running = True
        self.write_heartbeat()
        return True

    def status(self):
        uptime = None

        if (
            self.running
            and self.started_at is not None
        ):
            uptime = max(
                0.0,
                self.clock()
                - self.started_at,
            )

        return {
            "running": self.running,
            "unix_time": float(
                self.wall_clock()
            ),
            "uptime_seconds": (
                round(
                    uptime,
                    3,
                )
                if uptime is not None
                else None
            ),
            "llm_provider": getattr(
                self.assistant,
                "llm_provider",
                "unknown",
            ),
            "model": getattr(
                self.assistant,
                "model",
                "",
            ),
            "hardware_monitor": bool(
                self.hardware_monitor
                is not None
                and self.hardware_monitor.is_running
            ),
            "terminal_handoff": bool(
                self.terminal_handoff
                is not None
                and self.terminal_handoff.is_running
            ),
            "voice_handsfree": bool(
                self.voice_runner
                is not None
                and self.voice_runner.is_running
            ),
            "component_errors": dict(
                self.component_errors
            ),
            "last_error": self.last_error,
        }

    def write_heartbeat(self):
        return write_health_state(
            self.heartbeat_path,
            self.status(),
        )

    def wait(self):
        while not self.stop_event.wait(
            self.heartbeat_interval_seconds
        ):
            self.write_heartbeat()

        return True

    def stop(self):
        changed = self.running
        self.stop_event.set()

        timeout = max(
            0.0,
            float(
                self.runtime.get(
                    "shutdown_timeout_seconds",
                    10.0,
                )
            ),
        )

        if self.voice_runner is not None:
            try:
                self.voice_runner.stop(
                    timeout=timeout
                )
            except Exception as error:
                self._record_component_error(
                    "voice",
                    error,
                )

        if self.terminal_handoff is not None:
            try:
                self.terminal_handoff.stop()
            except Exception as error:
                self._record_component_error(
                    "terminal_handoff",
                    error,
                )

        if self.hardware_monitor is not None:
            try:
                self.hardware_monitor.stop(
                    timeout=min(
                        timeout,
                        5.0,
                    )
                )
            except Exception as error:
                self._record_component_error(
                    "hardware_monitor",
                    error,
                )

        self.running = False
        self.write_heartbeat()
        return changed
