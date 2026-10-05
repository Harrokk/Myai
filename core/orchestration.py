import re


SAFE_READ_ONLY_TOOLS = {
    "myai_health_status",
    "myai_recent_errors",
    "myai_audit_status",
    "myai_diagnostic_report",
    "memory_review_status",
    "ventuno_stability_report",
    "gpu_status",
    "cpu_status",
    "ram_status",
    "temperature_status",
    "disk_status",
    "usb_status",
    "camera_status",
    "bluetooth_status",
    "hardware_inventory",
    "hardware_changes",
    "geniex_status",
    "workspace_read",
    "workspace_list",
    "excel_read",
    "excel_list_sheets",
    "weather_forecast",
    "shopping_compare_sweden",
    "research_top_three",
    "source_verify_page",
    "web_fetch_text",
    "internet_search",
    "vision_analyze",
    "vision_detect_objects",
    "vision_read_text",
    "vision_detect_change",
}

LOCAL_CAPTURE_TOOLS = {
    "camera_capture",
}

VISION_TOOLS = {
    "vision_analyze",
    "vision_detect_objects",
    "vision_read_text",
    "vision_detect_change",
}

_EXPLICIT_CAPTURE_PHRASES = (
    "ta en bild",
    "ta bild",
    "ta ett foto",
    "ta foto",
    "fotografera",
    "capture image",
    "capture photo",
)

_SPLIT_PATTERN = re.compile(
    (
        r"\s*(?:[,;]|"
        r"\boch\b|\bsamt\b|\bsedan\b|\bdärefter\b|"
        r"\band\b|\bthen\b)\s*"
    ),
    flags=re.IGNORECASE,
)

_STATUS_HINTS = (
    (
        ("gpu", "grafikkort", "vram", "nvidia", "rtx"),
        "gpu_status",
    ),
    (
        ("cpu", "processor", "processorn"),
        "cpu_status",
    ),
    (
        (
            "ram",
            "arbetsminne",
            "ramminne",
            "ram-minne",
        ),
        "ram_status",
    ),
    (
        (
            "temperatur",
            "varm",
            "värme",
            "temperature",
        ),
        "temperature_status",
    ),
    (
        (
            "disk",
            "lagring",
            "utrymme",
            "storage",
        ),
        "disk_status",
    ),
)


def _config(
    settings,
):
    return (
        settings
        or {}
    ).get(
        "orchestration",
        {},
    )


def _split_clauses(
    user_input,
):
    text = " ".join(
        str(
            user_input
            or ""
        ).split()
    )

    if not text:
        return []

    clauses = [
        item.strip(
            " .?!"
        )
        for item in _SPLIT_PATTERN.split(
            text
        )
        if item.strip(
            " .?!"
        )
    ]

    return clauses or [
        text
    ]


def _status_hint_tools(
    clause,
):
    text = str(
        clause
        or ""
    ).lower()
    results = []

    for keywords, tool_name in _STATUS_HINTS:
        if any(
            keyword in text
            for keyword in keywords
        ):
            results.append(
                tool_name
            )

    return results


def _explicit_capture_requested(
    user_input,
):
    text = str(
        user_input
        or ""
    ).lower()

    return any(
        phrase in text
        for phrase in _EXPLICIT_CAPTURE_PHRASES
    )


def _tool_effect(
    tool_name,
):
    if tool_name in LOCAL_CAPTURE_TOOLS:
        return "local_capture"

    return "read_only"


def is_orchestration_safe_tool(
    tool_name,
    *,
    user_input,
    settings,
):
    if tool_name in SAFE_READ_ONLY_TOOLS:
        return True

    if tool_name in LOCAL_CAPTURE_TOOLS:
        config = _config(
            settings
        )
        return bool(
            config.get(
                "allow_local_capture",
                True,
            )
            and _explicit_capture_requested(
                user_input
            )
        )

    return False


def _dedupe_steps(
    steps,
):
    result = []
    seen = set()

    for step in steps:
        tool_name = step.get(
            "tool"
        )

        if (
            not tool_name
            or tool_name in seen
        ):
            continue

        seen.add(
            tool_name
        )
        result.append(
            step
        )

    return result


def _ordered_steps(
    steps,
):
    order = {
        "camera_capture": 10,
        "vision_analyze": 20,
        "vision_detect_objects": 20,
        "vision_read_text": 20,
        "vision_detect_change": 20,
    }

    indexed = list(
        enumerate(
            steps
        )
    )
    indexed.sort(
        key=lambda item: (
            order.get(
                item[
                    1
                ].get(
                    "tool"
                ),
                100,
            ),
            item[
                0
            ],
        )
    )
    return [
        item[
            1
        ]
        for item in indexed
    ]


def _safe_candidate_steps(
    user_input,
    *,
    available_tools,
    detect_function,
    settings,
):
    steps = []
    blocked = []
    clauses = _split_clauses(
        user_input
    )

    for clause in clauses:
        detected = list(
            detect_function(
                clause
            )
            or []
        )

        for hinted in _status_hint_tools(
            clause
        ):
            if hinted not in detected:
                detected.append(
                    hinted
                )

        for tool_name in detected:
            if tool_name not in available_tools:
                continue

            if not is_orchestration_safe_tool(
                tool_name,
                user_input=user_input,
                settings=settings,
            ):
                blocked.append(
                    tool_name
                )
                continue

            steps.append(
                {
                    "tool": tool_name,
                    "input": clause,
                    "effect": _tool_effect(
                        tool_name
                    ),
                }
            )

    direct = list(
        detect_function(
            user_input
        )
        or []
    )

    for tool_name in direct:
        if tool_name not in available_tools:
            continue

        if not is_orchestration_safe_tool(
            tool_name,
            user_input=user_input,
            settings=settings,
        ):
            blocked.append(
                tool_name
            )
            continue

        steps.append(
            {
                "tool": tool_name,
                "input": user_input,
                "effect": _tool_effect(
                    tool_name
                ),
            }
        )

    return (
        _ordered_steps(
            _dedupe_steps(
                steps
            )
        ),
        sorted(
            set(
                blocked
            )
        ),
    )


def build_safe_orchestration_plan(
    user_input,
    *,
    available_tools,
    detect_function,
    settings=None,
):
    config = _config(
        settings
    )

    if not config.get(
        "enabled",
        True,
    ):
        return {
            "enabled": False,
            "orchestrated": False,
            "source": "disabled",
            "steps": [],
            "blocked_tools": [],
        }

    try:
        max_tools = int(
            config.get(
                "max_tools",
                5,
            )
        )
    except (
        TypeError,
        ValueError,
    ):
        max_tools = 5

    max_tools = max(
        2,
        min(
            max_tools,
            8,
        ),
    )
    steps, blocked = _safe_candidate_steps(
        user_input,
        available_tools=available_tools,
        detect_function=detect_function,
        settings=settings,
    )

    if len(
        steps
    ) < 2:
        return {
            "enabled": True,
            "orchestrated": False,
            "source": "insufficient_safe_tools",
            "steps": steps,
            "blocked_tools": blocked,
        }

    selected = steps[
        :max_tools
    ]

    return {
        "enabled": True,
        "orchestrated": True,
        "source": "deterministic_safe",
        "steps": selected,
        "blocked_tools": blocked,
        "truncated": (
            len(
                steps
            )
            > max_tools
        ),
    }


def public_plan(
    plan,
):
    steps = []

    for step in (
        plan.get(
            "steps",
            []
        )
        or []
    ):
        steps.append(
            {
                "tool": step.get(
                    "tool"
                ),
                "effect": step.get(
                    "effect",
                    "read_only",
                ),
            }
        )

    return {
        "orchestrated": bool(
            plan.get(
                "orchestrated",
                False,
            )
        ),
        "source": plan.get(
            "source",
            "direct",
        ),
        "steps": steps,
        "blocked_tools": list(
            plan.get(
                "blocked_tools",
                []
            )
            or []
        ),
        "truncated": bool(
            plan.get(
                "truncated",
                False,
            )
        ),
    }
