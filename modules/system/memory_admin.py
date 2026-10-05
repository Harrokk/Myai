import re
from pathlib import Path

from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
)
from core.config import (
    PROJECT_ROOT,
    load_settings,
)
from core.memory import MemoryStore


def _memory_store(
    settings,
):
    raw = str(
        settings.get(
            "memory",
            {},
        ).get(
            "database",
            "memory.db",
        )
        or "memory.db"
    ).strip()
    path = Path(
        raw
    )

    if not path.is_absolute():
        path = (
            PROJECT_ROOT
            / path
        )

    store = MemoryStore(
        path,
        max_search_results=settings.get(
            "memory",
            {},
        ).get(
            "max_search_results",
            10,
        ),
    )
    store.init()
    return store


def _limit(
    settings,
):
    return max(
        1,
        min(
            int(
                settings.get(
                    "memory",
                    {},
                ).get(
                    "administration_limit",
                    50,
                )
            ),
            200,
        ),
    )


def _compact(
    value,
    limit=220,
):
    text = " ".join(
        str(
            value
            or ""
        ).split()
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


def _format_reviews(
    reviews,
    *,
    title,
):
    if not reviews:
        return (
            title
            + ": inga poster."
        )

    lines = [
        (
            f"{title} "
            f"({len(reviews)}):"
        )
    ]

    for item in reviews:
        conflicts = item.get(
            "conflict_ids",
            [],
        )
        suffix = (
            " | konflikter="
            + ",".join(
                str(
                    value
                )
                for value in conflicts
            )
            if conflicts
            else ""
        )
        lines.append(
            (
                f"- granskning #{item['id']} "
                f"[{item.get('category', 'other')}] "
                f"{_compact(item.get('content'))}"
                f"{suffix}"
            )
        )

    return "\n".join(
        lines
    )


def _format_stale(
    memories,
    days,
):
    if not memories:
        return (
            "Gamla aktiva minnen: inga poster äldre än "
            f"{days:g} dagar."
        )

    lines = [
        (
            "Gamla aktiva minnen "
            f"(≥ {days:g} dagar, {len(memories)}):"
        )
    ]

    for item in memories:
        lines.append(
            (
                f"- minne #{item['id']} "
                f"[{item.get('category', 'other')}] "
                f"{_compact(item.get('content'))} "
                f"| ålder={item.get('age_days', 'okänd')} dagar"
            )
        )

    return "\n".join(
        lines
    )


def _format_history(
    items,
):
    if not items:
        return "Minneshistorik: inga poster."

    lines = [
        f"Minneshistorik ({len(items)}):"
    ]

    for item in items:
        suffix = ""

        if item.get(
            "superseded_by"
        ):
            suffix += (
                " | ersatt_av="
                + str(
                    item[
                        "superseded_by"
                    ]
                )
            )

        lines.append(
            (
                f"- minne #{item['id']} "
                f"[{item.get('status', 'unknown')}] "
                f"[{item.get('category', 'other')}] "
                f"{_compact(item.get('content'))}"
                f"{suffix}"
            )
        )

    return "\n".join(
        lines
    )


def memory_review_status(
    user_input,
):
    settings = load_settings()
    store = _memory_store(
        settings
    )
    text = str(
        user_input
        or ""
    ).strip().lower()
    limit = _limit(
        settings
    )

    if any(
        phrase in text
        for phrase in (
            "minneskonflikt",
            "minneskonflikter",
            "konflikter i minnet",
            "konflikter i minnen",
        )
    ):
        return _format_reviews(
            store.list_reviews(
                status="pending",
                limit=limit,
                conflicts_only=True,
            ),
            title="Minnesgranskningar med konflikter",
        )

    if any(
        phrase in text
        for phrase in (
            "gamla minnen",
            "gamla minne",
            "stale minnen",
            "stale memory",
            "old memories",
        )
    ):
        match = re.search(
            r"(?:äldre än|older than)\s+(\d+)\s+(?:dagar|days)",
            text,
        )
        days = (
            float(
                match.group(
                    1
                )
            )
            if match
            else float(
                settings.get(
                    "memory",
                    {},
                ).get(
                    "stale_review_days",
                    365,
                )
            )
        )
        return _format_stale(
            store.list_stale(
                max_age_days=days,
                limit=limit,
            ),
            days,
        )

    if any(
        phrase in text
        for phrase in (
            "minneshistorik",
            "minne historik",
            "memory history",
        )
    ):
        return _format_history(
            store.get_history(
                limit=limit
            )
        )

    return _format_reviews(
        store.list_reviews(
            status="pending",
            limit=limit,
        ),
        title="Minnesgranskningar som väntar",
    )


def _audit_action(
    settings,
    *,
    action,
    target,
    details,
    operation,
):
    audit = AuditLogger(
        settings,
        PROJECT_ROOT,
    )
    audit.write_attempt(
        action=action,
        component="memory_admin",
        target=target,
        details=details,
    )

    try:
        result = operation()
    except Exception as error:
        audit.write_result(
            action=action,
            component="memory_admin",
            outcome=(
                audit_outcome_for_exception(
                    error
                )
            ),
            target=target,
            details={
                **details,
                "error_type": type(
                    error
                ).__name__,
            },
        )
        raise

    audit.write_result(
        action=action,
        component="memory_admin",
        outcome="success",
        target=target,
        details=details,
    )
    return result


def memory_review_action(
    user_input,
):
    settings = load_settings()
    store = _memory_store(
        settings
    )
    command = str(
        user_input
        or ""
    ).strip()

    approve = re.fullmatch(
        r"GODKÄNN MINNESGRANSKNING (\d+)",
        command,
    )

    if approve:
        review_id = int(
            approve.group(
                1
            )
        )
        try:
            memory_id = _audit_action(
                settings,
                action="memory_review_approve",
                target=(
                    f"memory_review/{review_id}"
                ),
                details={
                    "review_id": review_id,
                },
                operation=lambda: store.approve_review(
                    review_id
                ),
            )
        except Exception as error:
            return (
                "Minnesgranskningen kunde inte godkännas: "
                f"{error}"
            )

        return (
            f"Minnesgranskning {review_id} godkändes "
            f"som aktivt minne {memory_id}."
        )

    reject = re.fullmatch(
        r"AVVISA MINNESGRANSKNING (\d+)",
        command,
    )

    if reject:
        review_id = int(
            reject.group(
                1
            )
        )
        try:
            _audit_action(
                settings,
                action="memory_review_reject",
                target=(
                    f"memory_review/{review_id}"
                ),
                details={
                    "review_id": review_id,
                },
                operation=lambda: store.reject_review(
                    review_id
                ),
            )
        except Exception as error:
            return (
                "Minnesgranskningen kunde inte avvisas: "
                f"{error}"
            )

        return (
            f"Minnesgranskning {review_id} avvisades."
        )

    replace = re.fullmatch(
        (
            r"ERSÄTT MINNE (\d+) "
            r"MED GRANSKNING (\d+)"
        ),
        command,
    )

    if replace:
        memory_id = int(
            replace.group(
                1
            )
        )
        review_id = int(
            replace.group(
                2
            )
        )

        try:
            new_id = _audit_action(
                settings,
                action="memory_review_replace",
                target=(
                    f"memory/{memory_id}"
                ),
                details={
                    "review_id": review_id,
                    "target_memory_id": memory_id,
                },
                operation=lambda: store.replace_from_review(
                    review_id,
                    memory_id,
                ),
            )
        except Exception as error:
            return (
                "Minnet kunde inte ersättas: "
                f"{error}"
            )

        return (
            f"Minne {memory_id} ersattes av nytt minne "
            f"{new_id} från granskning {review_id}."
        )

    delete = re.fullmatch(
        r"RADERA MINNE (\d+)",
        command,
    )

    if delete:
        memory_id = int(
            delete.group(
                1
            )
        )

        if not settings.get(
            "memory",
            {},
        ).get(
            "permanent_delete_enabled",
            True,
        ):
            return (
                "Permanent minnesradering är avstängd "
                "i konfigurationen."
            )

        try:
            _audit_action(
                settings,
                action="memory_permanent_delete",
                target=(
                    f"memory/{memory_id}"
                ),
                details={
                    "memory_id": memory_id,
                },
                operation=lambda: (
                    store.delete_memory_permanently(
                        memory_id
                    )
                ),
            )
        except Exception as error:
            return (
                "Minnet kunde inte raderas: "
                f"{error}"
            )

        return (
            f"Minne {memory_id} raderades permanent."
        )

    return (
        "Ingen minnesändring gjordes. Använd exakt ett av följande format: "
        "GODKÄNN MINNESGRANSKNING <id>, "
        "AVVISA MINNESGRANSKNING <id>, "
        "ERSÄTT MINNE <minnes-id> MED GRANSKNING <gransknings-id>, "
        "eller RADERA MINNE <id>."
    )


TOOLS = {
    "memory_review_status": {
        "function": memory_review_status,
        "description": (
            "Visar read-only väntande minnesgranskningar, konflikter, "
            "gamla aktiva minnen eller minneshistorik."
        ),
        "pass_user_input": True,
    },
    "memory_review_action": {
        "function": memory_review_action,
        "description": (
            "Utför endast exakta, auditerade minnesadministrationskommandon "
            "för godkännande, avvisning, ersättning eller permanent radering."
        ),
        "pass_user_input": True,
    },
}
