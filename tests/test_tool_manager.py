from core import tool_manager


EXPECTED_TOOLS = {
    "gpu_status",
    "cpu_status",
    "ram_status",
    "temperature_status",
    "disk_status",
}


def test_load_tools_finds_existing_system_tools():
    tools = tool_manager.load_tools()
    assert EXPECTED_TOOLS.issubset(tools.keys())


def test_detect_tools_finds_cpu_and_ram_together():
    result = tool_manager.detect_tools(
        "Hur mycket CPU och RAM använder datorn?"
    )
    assert result == ["cpu_status", "ram_status"]


def test_detect_tools_finds_temperature():
    result = tool_manager.detect_tools("Hur varm är datorn?")
    assert result == ["temperature_status"]


def test_select_tools_uses_direct_detection_without_ai(monkeypatch):
    tools = {
        "cpu_status": {"function": lambda: "cpu", "description": "cpu"},
        "ram_status": {"function": lambda: "ram", "description": "ram"},
    }

    def fail_if_called(*args, **kwargs):
        raise AssertionError("AI fallback ska inte köras här")

    monkeypatch.setattr(
        tool_manager,
        "ai_detect_tools",
        fail_if_called,
    )

    result = tool_manager.select_tools(
        "Hur mycket CPU och RAM används?",
        tools,
        "http://localhost:11434/api/chat",
        "qwen3:8b",
    )

    assert result == ["cpu_status", "ram_status"]


def test_run_tools_runs_multiple_tools():
    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "cpu",
        },
        "ram_status": {
            "function": lambda: "RAM OK",
            "description": "ram",
        },
    }

    result = tool_manager.run_tools(
        ["cpu_status", "ram_status"],
        tools,
    )

    assert result == {
        "cpu_status": "CPU OK",
        "ram_status": "RAM OK",
    }


def test_run_tools_keeps_other_results_if_one_tool_fails():
    def broken():
        raise RuntimeError("testfel")

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "cpu",
        },
        "ram_status": {
            "function": broken,
            "description": "ram",
        },
    }

    result = tool_manager.run_tools(
        ["cpu_status", "ram_status"],
        tools,
    )

    assert result["cpu_status"] == "CPU OK"
    assert "testfel" in result["ram_status"]
