from pathlib import Path

from core.config import (
    PROJECT_ROOT,
    load_settings,
)
from core.ventuno_stability import (
    analyze_stability_log,
    format_stability_report,
)


def _analysis_config(
    settings,
):
    return settings.get(
        "stability_analysis",
        {},
    )


def _resolve_log_path(
    settings,
):
    config = _analysis_config(
        settings
    )
    raw = str(
        config.get(
            "log_path",
            "runtime/ventuno_stability.jsonl",
        )
        or "runtime/ventuno_stability.jsonl"
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


def read_ventuno_stability_report(
    settings=None,
):
    settings = (
        settings
        or load_settings()
    )
    config = _analysis_config(
        settings
    )
    logging_config = settings.get(
        "logging",
        {},
    )

    return analyze_stability_log(
        _resolve_log_path(
            settings
        ),
        backups=logging_config.get(
            "jsonl_backups",
            5,
        ),
        max_records=config.get(
            "max_records",
            10_000,
        ),
        target_hours=config.get(
            "target_hours",
            72.0,
        ),
        trend_fraction=config.get(
            "trend_fraction",
            0.25,
        ),
        latency_degradation_ratio=config.get(
            "latency_degradation_ratio",
            1.25,
        ),
    )


def ventuno_stability_report():
    return format_stability_report(
        read_ventuno_stability_report()
    )


TOOLS = {
    "ventuno_stability_report": {
        "function": ventuno_stability_report,
        "description": (
            "Analyserar read-only den lokala VENTUNO-stabilitetsloggen "
            "och visar latens, fel, backendbyten och resursdata utan "
            "att godkänna fysisk hårdvara."
        ),
    },
}
