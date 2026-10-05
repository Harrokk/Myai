import time
from pathlib import Path

from core.jsonl_log import append_jsonl


def _compact_message(
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
        64,
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


class ErrorLogger:
    """Best-effort structured error logging without raw user prompts."""

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
            "error_logging",
            {},
        )
        self.enabled = bool(
            config.get(
                "enabled",
                True,
            )
        )
        raw_path = str(
            config.get(
                "path",
                "runtime/errors.jsonl",
            )
            or ""
        ).strip()
        self.path = Path(
            raw_path
            or "runtime/errors.jsonl"
        )

        if not self.path.is_absolute():
            self.path = (
                self.project_root
                / self.path
            )

        self.max_message_chars = max(
            64,
            int(
                config.get(
                    "max_message_chars",
                    500,
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

    def log_exception(
        self,
        event,
        component,
        error,
    ):
        if not self.enabled:
            return False

        record = {
            "schema_version": 1,
            "written_unix_time": float(
                self.wall_clock()
            ),
            "event": _compact_message(
                event,
                max_chars=80,
            ),
            "component": _compact_message(
                component,
                max_chars=160,
            ),
            "error_type": type(
                error
            ).__name__,
            "message": _compact_message(
                error,
                max_chars=(
                    self.max_message_chars
                ),
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
        except Exception:
            return False
