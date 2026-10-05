import json
import os
from pathlib import Path
import tempfile
import time


DEFAULT_GENIEX_STATE = Path(
    "runtime/geniex_health.json"
)


def _safe_dict(value):
    return (
        dict(value)
        if isinstance(
            value,
            dict,
        )
        else {}
    )


def classify_health(
    llm_runtime,
    geniex_state=None,
):
    llm_runtime = _safe_dict(
        llm_runtime
    )
    geniex_state = _safe_dict(
        geniex_state
    )

    active_backend = str(
        llm_runtime.get(
            "active_backend",
            "primary",
        )
    ).lower()
    fallback_active = (
        active_backend
        == "fallback"
    )

    check = _safe_dict(
        geniex_state.get(
            "check",
        )
    )
    supervisor_enabled = (
        check.get(
            "enabled"
        )
        is not False
        and bool(
            geniex_state
        )
    )
    geniex_healthy = check.get(
        "healthy"
    )
    failures = int(
        check.get(
            "consecutive_failures",
            0,
        )
        or 0
    )

    if (
        supervisor_enabled
        and geniex_healthy is False
        and not fallback_active
    ):
        level = "unhealthy"
    elif (
        fallback_active
        or (
            supervisor_enabled
            and geniex_healthy is False
        )
        or failures > 0
    ):
        level = "degraded"
    else:
        level = "healthy"

    reasons = []

    if fallback_active:
        reasons.append(
            "LLM kör reservbackend."
        )

    if (
        supervisor_enabled
        and geniex_healthy is False
    ):
        reasons.append(
            "GenieX readiness är unhealthy."
        )

    if failures > 0:
        reasons.append(
            f"GenieX har {failures} misslyckade kontroller i rad."
        )

    llm_error = llm_runtime.get(
        "last_error"
    )

    if llm_error:
        reasons.append(
            f"Senaste LLM-fel: {llm_error}"
        )

    if not reasons:
        reasons.append(
            "Inga aktiva degraderingssignaler."
        )

    return {
        "level": level,
        "reasons": reasons,
        "fallback_active": (
            fallback_active
        ),
        "geniex_healthy": (
            geniex_healthy
        ),
        "geniex_consecutive_failures": (
            failures
        ),
    }


def build_health_status(
    llm_runtime,
    geniex_state=None,
):
    classification = classify_health(
        llm_runtime,
        geniex_state,
    )

    return {
        **classification,
        "llm_runtime": _safe_dict(
            llm_runtime
        ),
        "geniex": _safe_dict(
            geniex_state
        ),
    }


def read_health_state(path):
    target = Path(path)

    if not target.exists():
        return None

    try:
        data = json.loads(
            target.read_text(
                encoding="utf-8"
            )
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return None

    return (
        data
        if isinstance(
            data,
            dict,
        )
        else None
    )


def write_health_state(
    path,
    state,
):
    target = Path(path)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    payload = dict(
        state
    )
    payload[
        "written_unix_time"
    ] = time.time()

    descriptor, temp_name = (
        tempfile.mkstemp(
            prefix=(
                target.name
                + "."
            ),
            suffix=".tmp",
            dir=str(
                target.parent
            ),
        )
    )

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                payload,
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write(
                "\n"
            )
            handle.flush()
            os.fsync(
                handle.fileno()
            )

        os.replace(
            temp_name,
            target,
        )
    except Exception:
        try:
            os.unlink(
                temp_name
            )
        except OSError:
            pass
        raise

    return payload
