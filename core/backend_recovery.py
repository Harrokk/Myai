import math
import time
from pathlib import Path

from core.health_status import read_health_state


class HealthAwareBackendPolicy:
    """Choose primary/fallback from durable watchdog health with hysteresis."""

    def __init__(
        self,
        settings,
        project_root,
        *,
        clock=None,
    ):
        self.settings = settings
        self.project_root = Path(
            project_root
        )
        self.clock = (
            clock
            or time.time
        )
        self.config = (
            settings.get(
                "llm",
                {},
            )
            .get(
                "fallback",
                {},
            )
            .get(
                "health_aware",
                {},
            )
        )
        self.supervisor = settings.get(
            "geniex_supervisor",
            {},
        )
        self.last_reason = (
            "health-aware routing disabled"
        )
        self.fallback_activated_at = None

    @property
    def enabled(self):
        return bool(
            self.config.get(
                "enabled",
                False,
            )
        )

    def _state_path(self):
        raw = self.supervisor.get(
            "state_path",
            "runtime/geniex_health.json",
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

    def _state(self):
        return read_health_state(
            self._state_path()
        )

    def _is_stale(
        self,
        state,
    ):
        if not isinstance(
            state,
            dict,
        ):
            return True

        written = state.get(
            "written_unix_time"
        )

        try:
            now = float(self.clock())
            timestamp = float(written)
            stale_after = float(self.supervisor.get(
                "state_stale_seconds", 30.0
            ))
        except (TypeError, ValueError, OverflowError):
            return True

        # NaN timestamps can otherwise look recent forever; a far-future
        # timestamp from a corrupt/clock-skewed watchdog is not trustworthy.
        if not all(math.isfinite(x) for x in (now, timestamp, stale_after)):
            return True
        if stale_after < 0 or timestamp > now + 5.0:
            return True

        return bool(stale_after > 0 and now - timestamp > stale_after)

    def note_fallback_activation(
        self,
        reason=None,
    ):
        self.fallback_activated_at = float(
            self.clock()
        )

        if reason:
            self.last_reason = str(
                reason
            )

        return self.fallback_activated_at

    def note_primary_restored(
        self,
        reason=None,
    ):
        self.fallback_activated_at = None

        if reason:
            self.last_reason = str(
                reason
            )

    @staticmethod
    def _valid_counter(value):
        if isinstance(value, bool):
            return None
        try:
            # Reject fractional, NaN and infinite counters before int().
            number = float(value)
            if not math.isfinite(number) or not number.is_integer():
                return None
            count = int(number)
        except (TypeError, ValueError, OverflowError):
            return None
        return count if 0 <= count <= 1_000_000 else None

    def choose_backend(
        self,
        current_backend="primary",
    ):
        current = (
            "fallback"
            if str(
                current_backend
            ).lower()
            == "fallback"
            else "primary"
        )

        if not self.enabled:
            self.last_reason = (
                "health-aware routing disabled; try primary"
            )
            return "primary"

        state = self._state()

        if self._is_stale(
            state
        ):
            if current == "fallback":
                self.last_reason = (
                    "watchdog state stale; keep fallback"
                )
                return "fallback"

            self.last_reason = (
                "watchdog state stale; keep primary"
            )
            return "primary"

        check = (
            state.get(
                "check",
                {}
            )
            if isinstance(
                state,
                dict,
            )
            else {}
        )
        if not isinstance(check, dict):
            self.last_reason = "watchdog check invalid; preserve active backend"
            return current

        healthy = check.get("healthy")
        failures = self._valid_counter(check.get("consecutive_failures", 0))
        successes = self._valid_counter(check.get("consecutive_successes", 0))
        if (
            not isinstance(healthy, bool)
            or failures is None
            or successes is None
        ):
            self.last_reason = "watchdog counters invalid; preserve active backend"
            return current

        failure_threshold = max(
            1,
            int(
                self.config.get(
                    "failure_threshold",
                    self.supervisor.get(
                        "failure_threshold",
                        3,
                    ),
                )
            ),
        )
        recovery_threshold = max(
            1,
            int(
                self.config.get(
                    "recovery_success_threshold",
                    3,
                )
            ),
        )

        if (
            healthy is False
            and failures
            >= failure_threshold
        ):
            self.last_reason = (
                "watchdog failure threshold reached"
            )

            if current != "fallback":
                self.note_fallback_activation(
                    self.last_reason
                )

            return "fallback"

        if current == "fallback":
            written = state.get(
                "written_unix_time"
            )

            try:
                state_is_newer = (
                    self.fallback_activated_at
                    is None
                    or float(
                        written
                    )
                    > float(
                        self.fallback_activated_at
                    )
                )
            except (
                TypeError,
                ValueError,
            ):
                state_is_newer = False

            if (
                healthy is True
                and successes
                >= recovery_threshold
                and state_is_newer
            ):
                self.last_reason = (
                    "watchdog recovery threshold reached"
                )
                self.note_primary_restored(
                    self.last_reason
                )
                return "primary"

            self.last_reason = (
                "recovery threshold not reached; keep fallback"
            )
            return "fallback"

        self.last_reason = (
            "primary remains eligible"
        )
        return "primary"

    def status(self):
        return {
            "enabled": self.enabled,
            "last_reason": self.last_reason,
            "fallback_activated_at": (
                self.fallback_activated_at
            ),
        }
