import time
from pathlib import Path

from core.config import (
    PROJECT_ROOT,
    load_settings,
)
from core.health_status import (
    build_health_status,
    read_health_state,
)


def _resolve_path(
    settings,
    section,
    key,
    default,
):
    raw = (
        settings.get(
            section,
            {},
        )
        .get(
            key,
            default,
        )
    )
    path = Path(
        raw
    )

    if not path.is_absolute():
        path = (
            PROJECT_ROOT
            / path
        )

    return path


def _fallback_runtime(settings):
    llm = settings.get(
        "llm",
        {},
    )
    provider = str(
        llm.get(
            "provider",
            "ollama",
        )
    ).strip().lower()
    provider_config = (
        settings.get(
            "geniex",
            {},
        )
        if provider == "geniex"
        else settings.get(
            "ollama",
            {},
        )
    )

    return {
        "enabled": False,
        "active_backend": "primary",
        "primary_provider": provider,
        "primary_model": provider_config.get(
            "model",
            "",
        ),
        "fallback_provider": None,
        "fallback_model": None,
        "last_error": None,
        "provider": provider,
        "model": provider_config.get(
            "model",
            "",
        ),
    }


def read_myai_health(
    settings=None,
    *,
    now=None,
):
    settings = (
        settings
        or load_settings()
    )
    now = (
        time.time()
        if now is None
        else float(now)
    )
    health_config = settings.get(
        "health",
        {},
    )
    max_age = max(
        0.0,
        float(
            health_config.get(
                "state_stale_seconds",
                60.0,
            )
        ),
    )
    myai_path = _resolve_path(
        settings,
        "health",
        "state_path",
        "runtime/myai_health.json",
    )
    saved = read_health_state(
        myai_path
    )

    if saved is not None:
        written = saved.get(
            "written_unix_time"
        )

        try:
            age = (
                now
                - float(written)
            )
        except (
            TypeError,
            ValueError,
        ):
            age = None

        if (
            age is not None
            and age >= 0
            and (
                max_age <= 0
                or age <= max_age
            )
        ):
            result = dict(
                saved
            )
            result[
                "snapshot_age_seconds"
            ] = round(
                age,
                3,
            )
            result[
                "snapshot_stale"
            ] = False
            return result

    supervisor = settings.get(
        "geniex_supervisor",
        {},
    )
    geniex_path = _resolve_path(
        settings,
        "geniex_supervisor",
        "state_path",
        "runtime/geniex_health.json",
    )
    geniex_state = read_health_state(
        geniex_path
    )
    result = build_health_status(
        _fallback_runtime(
            settings
        ),
        geniex_state,
        supervisor_expected=bool(
            supervisor.get(
                "enabled",
                False,
            )
        ),
        stale_after_seconds=supervisor.get(
            "state_stale_seconds",
            30.0,
        ),
        now=now,
    )
    result[
        "snapshot_age_seconds"
    ] = None
    result[
        "snapshot_stale"
    ] = True
    return result


def format_myai_health(
    health,
):
    level = str(
        health.get(
            "level",
            "unknown",
        )
    )
    labels = {
        "healthy": "frisk",
        "degraded": "degraderad",
        "unhealthy": "ohälsosam",
        "unknown": "okänd",
    }
    runtime = health.get(
        "llm_runtime",
        {},
    )
    backend = runtime.get(
        "active_backend",
        "primary",
    )
    provider = runtime.get(
        "provider",
        runtime.get(
            "primary_provider",
            "okänd",
        ),
    )
    model = runtime.get(
        "model",
        runtime.get(
            "primary_model",
            "okänd",
        ),
    )
    lines = [
        (
            "MyAI-hälsa: "
            f"{labels.get(level, level)}"
        ),
        (
            "LLM: "
            f"{provider} / {model}"
        ),
        (
            "Aktiv backend: "
            f"{backend}"
        ),
    ]

    geniex_healthy = health.get(
        "geniex_healthy"
    )
    geniex_stale = bool(
        health.get(
            "geniex_state_stale",
            False,
        )
    )

    if geniex_stale:
        lines.append(
            "GenieX readiness: stale/unknown"
        )
    elif geniex_healthy is not None:
        lines.append(
            "GenieX readiness: "
            + (
                "ready"
                if geniex_healthy
                else "unhealthy"
            )
        )

    failures = int(
        health.get(
            "geniex_consecutive_failures",
            0,
        )
        or 0
    )

    if failures:
        lines.append(
            "GenieX-fel i rad: "
            f"{failures}"
        )

    successes = int(
        health.get(
            "geniex_consecutive_successes",
            0,
        )
        or 0
    )

    if successes:
        lines.append(
            "GenieX lyckade kontroller i rad: "
            f"{successes}"
        )

    routing_reason = (
        runtime.get(
            "routing_reason"
        )
    )

    if routing_reason:
        lines.append(
            "LLM-routing: "
            f"{routing_reason}"
        )

    reasons = health.get(
        "reasons",
        [],
    )

    for reason in reasons:
        lines.append(
            f"- {reason}"
        )

    if health.get(
        "snapshot_stale"
    ):
        lines.append(
            "Statuskälla: ingen färsk MyAI-snapshot; "
            "rapporten är rekonstruerad från tillgänglig runtime-status."
        )
    else:
        age = health.get(
            "snapshot_age_seconds"
        )

        if age is not None:
            lines.append(
                "Snapshot-ålder: "
                f"{age:.1f} s"
            )

    return "\n".join(
        lines
    )


def myai_health_status():
    return format_myai_health(
        read_myai_health()
    )


TOOLS = {
    "myai_health_status": {
        "function": myai_health_status,
        "description": (
            "Visar MyAI:s read-only hälsostatus, aktiv LLM-backend, "
            "fallbackläge och senaste GenieX-watchdogsignaler."
        ),
    },
}
