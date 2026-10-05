from datetime import datetime
from pathlib import Path

from core.config import (
    PROJECT_ROOT,
    load_settings,
)
from core.error_log import (
    read_recent_errors,
)


def _resolve_error_path(
    settings,
):
    raw = str(
        settings.get(
            "error_logging",
            {},
        ).get(
            "path",
            "runtime/errors.jsonl",
        )
        or "runtime/errors.jsonl"
    ).strip()
    path = Path(
        raw
    )

    if not path.is_absolute():
        path = (
            PROJECT_ROOT
            / path
        )

    return path


def read_myai_recent_errors(
    settings=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "error_logging",
        {},
    )

    if not config.get(
        "enabled",
        True,
    ):
        return {
            "enabled": False,
            "records": [],
            "count": 0,
            "malformed_count": 0,
        }

    logging_config = settings.get(
        "logging",
        {},
    )
    limit = min(
        50,
        max(
            1,
            int(
                config.get(
                    "recent_limit",
                    10,
                )
            ),
        ),
    )

    result = read_recent_errors(
        _resolve_error_path(
            settings
        ),
        limit=limit,
        backups=logging_config.get(
            "jsonl_backups",
            5,
        ),
        max_message_chars=config.get(
            "max_message_chars",
            500,
        ),
    )
    result[
        "enabled"
    ] = True
    return result


def _format_time(
    raw,
):
    try:
        return (
            datetime.fromtimestamp(
                float(
                    raw
                )
            )
            .astimezone()
            .isoformat(
                timespec="seconds"
            )
        )
    except (
        TypeError,
        ValueError,
        OSError,
        OverflowError,
    ):
        return "okänd tid"


def format_myai_recent_errors(
    result,
):
    if not result.get(
        "enabled",
        True,
    ):
        return (
            "MyAI:s lokala felloggning är avstängd."
        )

    records = result.get(
        "records",
        [],
    )

    if not records:
        text = (
            "Inga strukturerade MyAI-fel finns "
            "i den aktuella felloggen."
        )
    else:
        lines = [
            (
                "Senaste loggade MyAI-fel "
                f"({len(records)}):"
            )
        ]

        for item in records:
            lines.append(
                (
                    f"- {_format_time(item.get('written_unix_time'))} | "
                    f"{item.get('component', 'unknown')} | "
                    f"{item.get('error_type', 'Error')}: "
                    f"{item.get('message', '')}"
                )
            )

        text = "\n".join(
            lines
        )

    malformed = int(
        result.get(
            "malformed_count",
            0,
        )
        or 0
    )

    if malformed:
        text += (
            "\n"
            f"{malformed} ogiltig loggrad ignorerades."
        )

    return text


def myai_recent_errors():
    return format_myai_recent_errors(
        read_myai_recent_errors()
    )


TOOLS = {
    "myai_recent_errors": {
        "function": myai_recent_errors,
        "description": (
            "Visar de senaste strukturerade MyAI-felen "
            "read-only från den lokala roterande felloggen."
        ),
    },
}
