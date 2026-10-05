from datetime import datetime
from pathlib import Path

from core.audit_log import read_recent_audit
from core.config import (
    PROJECT_ROOT,
    load_settings,
)


def _resolve_audit_path(
    settings,
):
    raw = str(
        settings.get(
            "audit_logging",
            {},
        ).get(
            "path",
            "runtime/audit.jsonl",
        )
        or "runtime/audit.jsonl"
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


def _format_time(
    value,
):
    try:
        return (
            datetime.fromtimestamp(
                float(
                    value
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


def read_myai_audit_status(
    settings=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = settings.get(
        "audit_logging",
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
    result = read_recent_audit(
        _resolve_audit_path(
            settings
        ),
        limit=config.get(
            "recent_limit",
            20,
        ),
        backups=logging_config.get(
            "jsonl_backups",
            5,
        ),
    )
    result[
        "enabled"
    ] = True
    return result


def format_myai_audit_status(
    result,
):
    if not result.get(
        "enabled",
        True,
    ):
        return (
            "MyAI:s audit-loggning är avstängd."
        )

    records = result.get(
        "records",
        [],
    )

    if not records:
        text = (
            "Inga audit-händelser finns i den aktuella loggen."
        )
    else:
        lines = [
            (
                "Senaste MyAI audit-händelser "
                f"({len(records)}):"
            )
        ]

        for item in records:
            target = item.get(
                "target"
            )
            suffix = (
                f" | mål={target}"
                if target
                else ""
            )
            lines.append(
                (
                    f"- {_format_time(item.get('written_unix_time'))} | "
                    f"{item.get('action', 'unknown')} | "
                    f"{item.get('outcome', 'unknown')} | "
                    f"{item.get('component', 'unknown')}"
                    f"{suffix}"
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
            f"{malformed} ogiltig audit-rad ignorerades."
        )

    return text


def myai_audit_status():
    return format_myai_audit_status(
        read_myai_audit_status()
    )


TOOLS = {
    "myai_audit_status": {
        "function": myai_audit_status,
        "description": (
            "Visar read-only de senaste strukturerade audit-händelserna "
            "för skrivande och säkerhetsrelevanta MyAI-åtgärder."
        ),
    },
}
