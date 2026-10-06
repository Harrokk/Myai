import subprocess
import time
from urllib.parse import urljoin

import requests


class GenieXSupervisor:
    """Readiness monitor with explicit opt-in restart policy."""

    def __init__(
        self,
        settings,
        *,
        request_get=None,
        command_runner=None,
        clock=None,
    ):
        self.settings = settings
        self.geniex = settings.get(
            "geniex",
            {},
        )
        self.config = settings.get(
            "geniex_supervisor",
            {},
        )
        self.request_get = (
            request_get
            or requests.get
        )
        self.command_runner = (
            command_runner
            or self._default_command_runner
        )
        self.clock = (
            clock
            or time.monotonic
        )

        self.consecutive_failures = 0
        self.consecutive_successes = 0
        self.restart_attempts = 0
        self.last_restart_at = None
        self.last_check = None

    @property
    def enabled(self):
        return bool(
            self.config.get(
                "enabled",
                False,
            )
        )

    @property
    def restart_enabled(self):
        return bool(
            self.enabled
            and self.config.get(
                "restart_enabled",
                False,
            )
        )

    @property
    def models_url(self):
        base = str(
            self.geniex.get(
                "base_url",
                "http://127.0.0.1:18181/v1",
            )
        ).rstrip("/") + "/"

        return urljoin(
            base,
            "models",
        )

    @staticmethod
    def _default_command_runner(command, timeout):
        return subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _restart_command(self):
        raw = self.config.get(
            "restart_command",
            [],
        )

        if not isinstance(
            raw,
            list,
        ):
            raise ValueError(
                "GenieX restart_command måste vara en lista, inte shell-text."
            )

        command = [
            str(value)
            for value in raw
            if str(value).strip()
        ]

        if not command:
            raise ValueError(
                "GenieX restart är aktiverad men restart_command saknas."
            )

        return command

    def _restart_allowed_now(self):
        if not self.restart_enabled:
            return False

        max_attempts = max(
            0,
            int(
                self.config.get(
                    "max_restart_attempts",
                    3,
                )
            ),
        )

        if (
            max_attempts > 0
            and self.restart_attempts
            >= max_attempts
        ):
            return False

        if self.last_restart_at is None:
            return True

        cooldown = max(
            0.0,
            float(
                self.config.get(
                    "restart_cooldown_seconds",
                    60.0,
                )
            ),
        )

        return (
            self.clock()
            - self.last_restart_at
            >= cooldown
        )

    def check(self):
        if not self.enabled:
            result = {
                "enabled": False,
                "healthy": None,
                "status": "disabled",
                "models_url": self.models_url,
                "consecutive_failures": (
                    self.consecutive_failures
                ),
                "consecutive_successes": (
                    self.consecutive_successes
                ),
                "restart_attempts": (
                    self.restart_attempts
                ),
            }
            self.last_check = result
            return result

        timeout = max(
            0.1,
            float(
                self.config.get(
                    "health_timeout_seconds",
                    3.0,
                )
            ),
        )

        try:
            response = self.request_get(
                self.models_url,
                timeout=timeout,
            )
            response.raise_for_status()
            payload = response.json()

            if not isinstance(
                payload,
                dict,
            ):
                raise ValueError(
                    "GenieX /v1/models returnerade inte ett JSON-objekt."
                )

            models = payload.get(
                "data",
            )

            if not isinstance(
                models,
                list,
            ):
                raise ValueError(
                    "GenieX /v1/models saknar listan data."
                )

            self.consecutive_failures = 0
            self.consecutive_successes += 1
            result = {
                "enabled": True,
                "healthy": True,
                "status": "ready",
                "models_url": self.models_url,
                "model_count": len(
                    models
                ),
                "consecutive_failures": 0,
                "consecutive_successes": (
                    self.consecutive_successes
                ),
                "restart_attempts": (
                    self.restart_attempts
                ),
                "error": None,
            }
        except Exception as error:
            self.consecutive_failures += 1
            self.consecutive_successes = 0
            result = {
                "enabled": True,
                "healthy": False,
                "status": "unhealthy",
                "models_url": self.models_url,
                "model_count": None,
                "consecutive_failures": (
                    self.consecutive_failures
                ),
                "consecutive_successes": 0,
                "restart_attempts": (
                    self.restart_attempts
                ),
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
            }

        self.last_check = result
        return result

    def restart(self):
        if not self._restart_allowed_now():
            return {
                "attempted": False,
                "success": False,
                "reason": (
                    "restart är avstängd, maxförsök nått "
                    "eller cooldown pågår"
                ),
                "restart_attempts": (
                    self.restart_attempts
                ),
            }

        command = self._restart_command()
        timeout = max(
            1.0,
            float(
                self.config.get(
                    "restart_timeout_seconds",
                    30.0,
                )
            ),
        )

        self.restart_attempts += 1
        self.last_restart_at = (
            self.clock()
        )

        try:
            result = self.command_runner(
                command,
                timeout,
            )
            returncode = int(
                getattr(
                    result,
                    "returncode",
                    1,
                )
            )
            success = (
                returncode == 0
            )
            stdout = str(
                getattr(
                    result,
                    "stdout",
                    "",
                )
                or ""
            ).strip()
            stderr = str(
                getattr(
                    result,
                    "stderr",
                    "",
                )
                or ""
            ).strip()

            return {
                "attempted": True,
                "success": success,
                "returncode": returncode,
                "stdout": stdout,
                "stderr": stderr,
                "restart_attempts": (
                    self.restart_attempts
                ),
            }
        except Exception as error:
            return {
                "attempted": True,
                "success": False,
                "error": (
                    f"{type(error).__name__}: "
                    f"{error}"
                ),
                "restart_attempts": (
                    self.restart_attempts
                ),
            }

    def supervise_once(self):
        check = self.check()
        threshold = max(
            1,
            int(
                self.config.get(
                    "failure_threshold",
                    3,
                )
            ),
        )

        if (
            check.get(
                "healthy"
            )
            is False
            and self.consecutive_failures
            >= threshold
        ):
            restart = self.restart()
        else:
            restart = {
                "attempted": False,
                "success": False,
                "reason": (
                    "restarttröskeln är inte uppnådd"
                ),
                "restart_attempts": (
                    self.restart_attempts
                ),
            }

        return {
            "check": check,
            "restart": restart,
        }
