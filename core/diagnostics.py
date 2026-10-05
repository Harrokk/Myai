import json
import time
from pathlib import Path

from core.audit_log import read_recent_audit
from core.config_validation import validate_settings
from core.deployment_lock import (
    load_lock_manifest,
    resolve_project_path,
    validate_lock_manifest,
)
from core.error_log import read_recent_errors
from core.health_status import read_health_state
from modules.system.health import read_myai_health


def _resolve_path(
    project_root,
    raw,
):
    path = Path(
        str(
            raw
            or ""
        )
    )

    if not path.is_absolute():
        path = (
            Path(
                project_root
            )
            / path
        )

    return path


def _snapshot_status(
    path,
    *,
    now,
    stale_after_seconds,
):
    state = read_health_state(
        path
    )

    if state is None:
        return {
            "present": False,
            "stale": True,
            "age_seconds": None,
            "state": None,
        }

    written = state.get(
        "written_unix_time"
    )
    age = None

    try:
        age = max(
            0.0,
            float(
                now
            )
            - float(
                written
            ),
        )
    except (
        TypeError,
        ValueError,
    ):
        pass

    stale_limit = max(
        0.0,
        float(
            stale_after_seconds
        ),
    )
    stale = (
        age is None
        or (
            stale_limit > 0
            and age > stale_limit
        )
    )

    return {
        "present": True,
        "stale": bool(
            stale
        ),
        "age_seconds": (
            round(
                age,
                3,
            )
            if age is not None
            else None
        ),
        "state": state,
    }


def _provider_status(
    settings,
):
    llm = settings.get(
        "llm",
        {},
    )
    provider = str(
        llm.get(
            "provider",
            "ollama",
        )
        or "ollama"
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
    fallback = llm.get(
        "fallback",
        {},
    )

    return {
        "primary_provider": provider,
        "primary_model": str(
            provider_config.get(
                "model",
                "",
            )
            or ""
        ),
        "fallback_enabled": bool(
            fallback.get(
                "enabled",
                False,
            )
        ),
        "fallback_provider": str(
            fallback.get(
                "provider",
                "",
            )
            or ""
        ),
        "fallback_model": str(
            fallback.get(
                "model",
                "",
            )
            or ""
        ),
        "vision_enabled": bool(
            settings.get(
                "vision",
                {},
            ).get(
                "enabled",
                False,
            )
        ),
        "ventuno_enabled": bool(
            settings.get(
                "ventuno",
                {},
            ).get(
                "enabled",
                False,
            )
        ),
    }


def _deployment_lock_status(
    settings,
    project_root,
):
    config = settings.get(
        "deployment_lock",
        {},
    )
    required = bool(
        config.get(
            "required",
            False,
        )
    )
    raw_path = str(
        config.get(
            "lock_path",
            "config/ventuno_stack_lock.json",
        )
        or ""
    ).strip()

    result = {
        "required": required,
        "path": raw_path,
        "present": False,
        "structurally_valid": False,
        "blocking": False,
        "errors": [],
        "observed_stack_compared": False,
        "note": (
            "Endast manifestets struktur kontrolleras här; "
            "observerad VENTUNO-stack jämförs inte."
        ),
    }

    if not raw_path:
        result[
            "blocking"
        ] = required
        result[
            "errors"
        ] = [
            "Deployment-lock path saknas."
        ]
        return result

    path = resolve_project_path(
        project_root,
        raw_path,
    )

    if not path.exists():
        result[
            "blocking"
        ] = required
        result[
            "errors"
        ] = (
            [
                "Deployment-lockfil saknas."
            ]
            if required
            else []
        )
        return result

    result[
        "present"
    ] = True

    try:
        manifest = load_lock_manifest(
            path
        )
        errors = validate_lock_manifest(
            manifest
        )
    except Exception as error:
        errors = [
            (
                f"{type(error).__name__}: "
                f"{error}"
            )
        ]

    result[
        "errors"
    ] = list(
        errors
    )
    result[
        "structurally_valid"
    ] = not errors
    result[
        "blocking"
    ] = bool(
        required
        and errors
    )
    return result


def _recent_error_status(
    settings,
    project_root,
):
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
            "count": 0,
            "malformed_count": 0,
            "records": [],
        }

    path = _resolve_path(
        project_root,
        config.get(
            "path",
            "runtime/errors.jsonl",
        ),
    )
    logging_config = settings.get(
        "logging",
        {},
    )
    result = read_recent_errors(
        path,
        limit=config.get(
            "recent_limit",
            10,
        ),
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


def _recent_audit_status(
    settings,
    project_root,
):
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
            "count": 0,
            "malformed_count": 0,
            "records": [],
        }

    path = _resolve_path(
        project_root,
        config.get(
            "path",
            "runtime/audit.jsonl",
        ),
    )
    logging_config = settings.get(
        "logging",
        {},
    )
    result = read_recent_audit(
        path,
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


def build_diagnostic_report(
    settings,
    project_root,
    *,
    now=None,
):
    """Combine read-only MyAI diagnostics without preflight or hardware writes."""

    now = (
        time.time()
        if now is None
        else float(
            now
        )
    )
    ventuno_enabled = bool(
        settings.get(
            "ventuno",
            {},
        ).get(
            "enabled",
            False,
        )
    )
    validation = validate_settings(
        settings,
        require_ventuno_profile=(
            ventuno_enabled
        ),
    )
    health = read_myai_health(
        settings,
        now=now,
    )

    runtime_config = settings.get(
        "runtime",
        {},
    )
    heartbeat_interval = max(
        1.0,
        float(
            runtime_config.get(
                "heartbeat_interval_seconds",
                10.0,
            )
        ),
    )
    diagnostics_config = settings.get(
        "diagnostics",
        {},
    )
    runtime_stale = max(
        heartbeat_interval
        * 3.0,
        float(
            diagnostics_config.get(
                "runtime_stale_seconds",
                30.0,
            )
        ),
    )
    runtime_path = _resolve_path(
        project_root,
        runtime_config.get(
            "heartbeat_path",
            "runtime/myai_runtime.json",
        ),
    )
    runtime = _snapshot_status(
        runtime_path,
        now=now,
        stale_after_seconds=runtime_stale,
    )
    errors = _recent_error_status(
        settings,
        project_root,
    )
    audit = _recent_audit_status(
        settings,
        project_root,
    )
    deployment = _deployment_lock_status(
        settings,
        project_root,
    )
    provider = _provider_status(
        settings
    )

    concerns = []

    if not validation[
        "valid"
    ]:
        concerns.append(
            "Konfigurationen har blockerande valideringsfel."
        )

    if health.get(
        "level"
    ) in {
        "degraded",
        "unhealthy",
        "unknown",
    }:
        concerns.append(
            (
                "MyAI health är "
                f"{health.get('level', 'unknown')}."
            )
        )

    if runtime[
        "present"
    ] and runtime[
        "stale"
    ]:
        concerns.append(
            "Runtime-heartbeat finns men är stale."
        )

    if deployment[
        "blocking"
    ]:
        concerns.append(
            "Deployment-lock har blockerande strukturfel."
        )

    if errors.get(
        "count",
        0,
    ):
        concerns.append(
            (
                f"{errors.get('count', 0)} senaste "
                "strukturerade fel finns i felloggen."
            )
        )

    return {
        "schema_version": 1,
        "read_only": True,
        "physical_preflight_executed": False,
        "physical_hardware_approval": False,
        "generated_unix_time": float(
            now
        ),
        "configuration": {
            "valid": bool(
                validation[
                    "valid"
                ]
            ),
            "errors": list(
                validation[
                    "errors"
                ]
            ),
            "warnings": list(
                validation[
                    "warnings"
                ]
            ),
        },
        "provider": provider,
        "health": health,
        "runtime": runtime,
        "deployment_lock": deployment,
        "recent_errors": errors,
        "recent_audit": audit,
        "concerns": concerns,
        "notes": [
            (
                "Rapporten läser endast lokal konfiguration, "
                "snapshots och loggar."
            ),
            (
                "VENTUNO preflight, GenieX CLI-kommandon, "
                "modellinference och fysisk I/O körs inte."
            ),
            (
                "Rapporten kan därför inte godkänna fysisk VENTUNO-hårdvara."
            ),
        ],
    }


def _yn(
    value,
):
    return (
        "ja"
        if value
        else "nej"
    )


def format_diagnostic_report(
    report,
):
    config = report.get(
        "configuration",
        {},
    )
    provider = report.get(
        "provider",
        {},
    )
    health = report.get(
        "health",
        {},
    )
    runtime = report.get(
        "runtime",
        {},
    )
    deployment = report.get(
        "deployment_lock",
        {},
    )
    errors = report.get(
        "recent_errors",
        {},
    )
    audit = report.get(
        "recent_audit",
        {},
    )

    lines = [
        "MyAI samlad diagnostik",
        (
            "Konfiguration giltig: "
            + _yn(
                config.get(
                    "valid",
                    False,
                )
            )
            + f" | fel={len(config.get('errors', []))}"
            + f" | varningar={len(config.get('warnings', []))}"
        ),
        (
            "LLM: "
            f"{provider.get('primary_provider', 'unknown')} / "
            f"{provider.get('primary_model', '')}"
        ),
        (
            "Fallback aktiverad: "
            + _yn(
                provider.get(
                    "fallback_enabled",
                    False,
                )
            )
        ),
        (
            "MyAI health: "
            f"{health.get('level', 'unknown')}"
        ),
        (
            "Runtime-heartbeat: "
            + (
                "saknas"
                if not runtime.get(
                    "present"
                )
                else (
                    "stale"
                    if runtime.get(
                        "stale"
                    )
                    else "färsk"
                )
            )
        ),
        (
            "Deployment-lock: "
            f"required={_yn(deployment.get('required', False))}, "
            f"present={_yn(deployment.get('present', False))}, "
            f"structurally_valid={_yn(deployment.get('structurally_valid', False))}"
        ),
        (
            "Senaste felloggsposter: "
            f"{int(errors.get('count', 0) or 0)}"
        ),
        (
            "Senaste audit-händelser: "
            f"{int(audit.get('count', 0) or 0)}"
        ),
    ]

    concerns = report.get(
        "concerns",
        [],
    )

    if concerns:
        lines.append(
            "Observationer:"
        )

        for item in concerns:
            lines.append(
                f"- {item}"
            )

    lines.extend(
        [
            "Fysisk preflight körd: nej",
            (
                "Fysisk VENTUNO-verifiering: inte bedömd; "
                "rapporten är read-only."
            ),
        ]
    )

    return "\n".join(
        lines
    )
