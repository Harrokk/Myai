import time
from pathlib import Path

from core.jsonl_log import append_jsonl


_ALLOWED_OUTCOMES = {
    "attempt",
    "success",
    "denied",
    "failed",
}


def _compact(
    value,
    *,
    max_chars,
):
    text = " ".join(
        str(
            value
            or ""
        ).split()
    )
    limit = max(
        16,
        int(
            max_chars
        ),
    )

    if len(
        text
    ) <= limit:
        return text

    return (
        text[
            : limit - 3
        ]
        + "..."
    )


def audit_outcome_for_exception(
    error,
):
    if isinstance(
        error,
        PermissionError,
    ):
        return "denied"

    message = str(
        error
        or ""
    ).lower()

    if any(
        phrase in message
        for phrase in (
            "avstängd",
            "inte tillåten",
            "inte tillåtet",
            "permission",
            "vägrar",
            "kräver",
        )
    ):
        return "denied"

    return "failed"


class AuditLogger:
    """Structured action audit log without prompts, secrets or payload content."""

    def __init__(
        self,
        settings,
        project_root,
        *,
        wall_clock=None,
    ):
        self.settings = settings
        self.project_root = Path(
            project_root
        )
        self.wall_clock = (
            wall_clock
            or time.time
        )
        config = settings.get(
            "audit_logging",
            {},
        )
        self.enabled = bool(
            config.get(
                "enabled",
                True,
            )
        )
        self.require_for_writes = bool(
            config.get(
                "require_for_writes",
                True,
            )
        )
        raw_path = str(
            config.get(
                "path",
                "runtime/audit.jsonl",
            )
            or ""
        ).strip()
        self.path = Path(
            raw_path
            or "runtime/audit.jsonl"
        )

        if not self.path.is_absolute():
            self.path = (
                self.project_root
                / self.path
            )

        self.max_detail_chars = max(
            32,
            int(
                config.get(
                    "max_detail_chars",
                    200,
                )
            ),
        )
        logging_config = settings.get(
            "logging",
            {},
        )
        self.max_bytes = max(
            0,
            int(
                logging_config.get(
                    "jsonl_max_bytes",
                    5_000_000,
                )
            ),
        )
        self.backups = max(
            0,
            int(
                logging_config.get(
                    "jsonl_backups",
                    5,
                )
            ),
        )

    def _details(
        self,
        details,
    ):
        if not isinstance(
            details,
            dict,
        ):
            return {}

        sanitized = {}

        for key, value in details.items():
            name = _compact(
                key,
                max_chars=64,
            )

            if isinstance(
                value,
                bool,
            ) or value is None:
                sanitized[
                    name
                ] = value
            elif isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):
                sanitized[
                    name
                ] = value
            else:
                sanitized[
                    name
                ] = _compact(
                    value,
                    max_chars=(
                        self.max_detail_chars
                    ),
                )

        return sanitized

    def log(
        self,
        *,
        action,
        component,
        outcome,
        target=None,
        details=None,
        required=False,
    ):
        outcome_value = str(
            outcome
        ).strip().lower()

        if outcome_value not in _ALLOWED_OUTCOMES:
            raise ValueError(
                "Ogiltigt audit-utfall."
            )

        must_write = bool(
            required
        )

        if not self.enabled:
            if must_write:
                raise RuntimeError(
                    "Audit-loggning krävs för denna skrivåtgärd men är avstängd."
                )

            return False

        record = {
            "schema_version": 1,
            "written_unix_time": float(
                self.wall_clock()
            ),
            "action": _compact(
                action,
                max_chars=96,
            ),
            "component": _compact(
                component,
                max_chars=96,
            ),
            "outcome": outcome_value,
            "target": (
                _compact(
                    target,
                    max_chars=240,
                )
                if target
                else None
            ),
            "details": self._details(
                details
            ),
        }

        try:
            append_jsonl(
                self.path,
                record,
                max_bytes=self.max_bytes,
                backups=self.backups,
            )
            return True
        except Exception as error:
            if must_write:
                raise RuntimeError(
                    "Audit-loggen kunde inte skrivas; skrivåtgärden blockeras."
                ) from error

            return False

    def write_attempt(
        self,
        *,
        action,
        component,
        target=None,
        details=None,
    ):
        return self.log(
            action=action,
            component=component,
            outcome="attempt",
            target=target,
            details=details,
            required=(
                self.require_for_writes
            ),
        )

    def write_result(
        self,
        *,
        action,
        component,
        outcome,
        target=None,
        details=None,
    ):
        return self.log(
            action=action,
            component=component,
            outcome=outcome,
            target=target,
            details=details,
            required=False,
        )
