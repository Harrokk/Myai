from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from core.orchestration import (
    build_safe_orchestration_plan,
    public_plan,
)
from core import tool_manager


class FailLLM:
    def chat(
        self,
        messages,
        timeout=120,
    ):
        raise AssertionError(
            "LLM-routing ska inte behövas."
        )


def tools(*names):
    return {
        name: {
            "function": lambda: name,
            "description": name,
        }
        for name in names
    }


def test_orchestration_combines_weather_and_ram_with_clause_inputs():
    available = {
        "weather_forecast": {
            "function": lambda query: query,
            "description": "weather",
            "pass_user_input": True,
        },
        "ram_status": {
            "function": lambda: "ram",
            "description": "ram",
        },
    }
    settings = deepcopy(
        DEFAULT_SETTINGS
    )

    plan = tool_manager.select_tool_plan(
        (
            "Vad blir det för väder i Stockholm idag "
            "och hur mycket RAM används?"
        ),
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "orchestrated"
    ] is True
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "weather_forecast",
        "ram_status",
    ]
    assert plan[
        "steps"
    ][
        0
    ][
        "input"
    ] == (
        "Vad blir det för väder i Stockholm idag"
    )


def test_orchestration_orders_capture_before_vision_and_other_tools():
    available = tools(
        "camera_capture",
        "vision_analyze",
        "cpu_status",
    )
    settings = deepcopy(
        DEFAULT_SETTINGS
    )

    plan = tool_manager.select_tool_plan(
        (
            "Ta en bild och analysera bilden "
            "och visa CPU status"
        ),
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "orchestrated"
    ] is True
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "camera_capture",
        "vision_analyze",
        "cpu_status",
    ]
    assert plan[
        "steps"
    ][
        0
    ][
        "effect"
    ] == "local_capture"


def test_local_capture_is_not_planner_safe_without_explicit_capture_request():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    available = tools(
        "camera_capture",
        "vision_analyze",
        "cpu_status",
    )

    def detect(
        text,
    ):
        if "analysera" in text.lower():
            return [
                "camera_capture",
                "vision_analyze",
            ]

        if "cpu" in text.lower():
            return [
                "cpu_status"
            ]

        return []

    plan = build_safe_orchestration_plan(
        (
            "Analysera bilden och visa CPU status"
        ),
        available_tools=available,
        detect_function=detect,
        settings=settings,
    )

    assert "camera_capture" in plan[
        "blocked_tools"
    ]
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "vision_analyze",
        "cpu_status",
    ]


def test_planner_respects_local_capture_disable_flag():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "orchestration"
    ][
        "allow_local_capture"
    ] = False
    available = tools(
        "camera_capture",
        "vision_analyze",
        "cpu_status",
    )

    plan = build_safe_orchestration_plan(
        (
            "Ta en bild och analysera bilden "
            "och visa CPU status"
        ),
        available_tools=available,
        detect_function=tool_manager.detect_tools,
        settings=settings,
    )

    assert "camera_capture" in plan[
        "blocked_tools"
    ]
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "vision_analyze",
        "cpu_status",
    ]


def test_direct_destructive_memory_action_is_never_expanded():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    available = tools(
        "memory_review_action",
        "cpu_status",
    )
    available[
        "memory_review_action"
    ][
        "pass_user_input"
    ] = True

    plan = tool_manager.select_tool_plan(
        "RADERA MINNE 7 och visa CPU status",
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "orchestrated"
    ] is False
    assert plan[
        "source"
    ] == "direct_non_orchestrated"
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "memory_review_action",
    ]


def test_public_plan_does_not_expose_clause_input():
    plan = {
        "orchestrated": True,
        "source": "deterministic_safe",
        "steps": [
            {
                "tool": "internet_search",
                "input": "hemlig delquery",
                "effect": "read_only",
            }
        ],
        "blocked_tools": [],
    }

    result = public_plan(
        plan
    )

    assert result[
        "steps"
    ] == [
        {
            "tool": "internet_search",
            "effect": "read_only",
        }
    ]
    assert "hemlig delquery" not in str(
        result
    )


def test_orchestration_max_tools_truncates_deterministically():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "orchestration"
    ][
        "max_tools"
    ] = 2
    available = tools(
        "cpu_status",
        "ram_status",
        "disk_status",
    )

    plan = tool_manager.select_tool_plan(
        "CPU och RAM och disk status",
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "orchestrated"
    ] is True
    assert plan[
        "truncated"
    ] is True
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "cpu_status",
        "ram_status",
    ]


def test_run_tools_uses_per_tool_query_and_bounds_result():
    seen = {}
    available = {
        "internet_search": {
            "function": lambda query: (
                seen.setdefault(
                    "query",
                    query,
                )
                and (
                    "x"
                    * 1000
                )
            ),
            "description": "search",
            "pass_user_input": True,
        },
    }

    result = tool_manager.run_tools(
        [
            "internet_search"
        ],
        available,
        user_input="hela frågan",
        tool_inputs={
            "internet_search": (
                "sök på internet efter test"
            ),
        },
        result_char_limit=256,
    )

    assert seen[
        "query"
    ] == "sök på internet efter test"
    assert len(
        result[
            "internet_search"
        ]
    ) <= 256
    assert "trunkerat" in result[
        "internet_search"
    ]


def test_orchestration_disabled_preserves_direct_behavior():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "orchestration"
    ][
        "enabled"
    ] = False
    available = {
        "weather_forecast": {
            "function": lambda query: query,
            "description": "weather",
            "pass_user_input": True,
        },
        "ram_status": {
            "function": lambda: "ram",
            "description": "ram",
        },
    }

    plan = tool_manager.select_tool_plan(
        (
            "Vad blir det för väder i Stockholm idag "
            "och hur mycket RAM används?"
        ),
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "orchestrated"
    ] is False
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "weather_forecast"
    ]


class WriteChoosingLLM:
    def __init__(self):
        self.prompt = ""

    def chat(
        self,
        messages,
        timeout=120,
    ):
        self.prompt = messages[
            0
        ][
            "content"
        ]
        return "workspace_write"


def test_llm_fallback_cannot_select_write_tool_when_orchestration_enabled():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    llm = WriteChoosingLLM()
    available = {
        "workspace_write": {
            "function": lambda query: "WRITE",
            "description": "write",
            "pass_user_input": True,
        },
        "cpu_status": {
            "function": lambda: "CPU",
            "description": "cpu",
        },
    }

    plan = tool_manager.select_tool_plan(
        "Gör något okänt med systemet.",
        available,
        llm,
        settings=settings,
    )

    assert plan[
        "source"
    ] == "llm_safe_fallback"
    assert plan[
        "steps"
    ] == []
    assert "workspace_write" not in llm.prompt


def test_explicit_workspace_write_keeps_existing_direct_route():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    available = {
        "workspace_write": {
            "function": lambda query: "WRITE",
            "description": "write",
            "pass_user_input": True,
        },
        "cpu_status": {
            "function": lambda: "CPU",
            "description": "cpu",
        },
    }

    plan = tool_manager.select_tool_plan(
        'Skapa fil "test.txt" med innehållet hej.',
        available,
        FailLLM(),
        settings=settings,
    )

    assert plan[
        "source"
    ] == "direct_non_orchestrated"
    assert [
        step[
            "tool"
        ]
        for step in plan[
            "steps"
        ]
    ] == [
        "workspace_write",
    ]


def test_snapshot_mutating_hardware_changes_is_not_orchestration_safe():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    available = tools(
        "hardware_changes",
        "ram_status",
    )

    def detect(
        text,
    ):
        result = []

        if "hårdvara" in text.lower():
            result.append(
                "hardware_changes"
            )

        if "ram" in text.lower():
            result.append(
                "ram_status"
            )

        return result

    plan = build_safe_orchestration_plan(
        "Kontrollera hårdvaruförändringar och RAM",
        available_tools=available,
        detect_function=detect,
        settings=settings,
    )

    assert "hardware_changes" in plan[
        "blocked_tools"
    ]
    assert plan[
        "orchestrated"
    ] is False
