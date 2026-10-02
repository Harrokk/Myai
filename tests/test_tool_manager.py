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


def test_detect_tools_finds_usb():
    result = tool_manager.detect_tools(
        "Vilka USB-enheter är inkopplade?"
    )
    assert result == ["usb_status"]


def test_detect_tools_finds_camera():
    result = tool_manager.detect_tools(
        "Vilka kameror är anslutna?"
    )
    assert result == ["camera_status"]


def test_detect_tools_finds_bluetooth():
    result = tool_manager.detect_tools(
        "Vilka Bluetooth-enheter finns?"
    )
    assert result == ["bluetooth_status"]


def test_detect_tools_routes_bluetooth_distance_to_proximity():
    result = tool_manager.detect_tools(
        "Hur långt bort är Bluetooth-enheterna i närheten?"
    )
    assert result == ["bluetooth_nearby"]


def test_detect_tools_routes_raspberry_pi_status():
    result = tool_manager.detect_tools(
        "Hur mår min Raspberry Pi 5, är den varm eller throttlar?"
    )
    assert result == ["pi_system_status"]


def test_detect_tools_routes_pi_bus_devices():
    result = tool_manager.detect_tools(
        "Vilka I2C-enheter och SPI-enheter finns på min Raspberry Pi?"
    )
    assert result == ["pi_bus_devices_status"]


def test_detect_tools_routes_raspberry_pi_gpio_reference():
    result = tool_manager.detect_tools(
        "Vilken GPIO ska jag använda för I2C på Raspberry Pi?"
    )
    assert result == ["pi_gpio_reference"]


def test_detect_tools_routes_explicit_gpio_without_pi_name():
    result = tool_manager.detect_tools(
        "Kan jag koppla en 5 V-signal till GPIO17?"
    )
    assert result == ["pi_gpio_reference"]


def test_detect_tools_routes_pi_interface_inventory():
    result = tool_manager.detect_tools(
        "Vilka gränssnitt och portar finns på min Raspberry Pi?"
    )
    assert result == ["pi_interfaces_status"]


def test_detect_tools_routes_pi_power_status():
    result = tool_manager.detect_tools(
        "Hur mycket ström drar min Raspberry Pi i watt?"
    )
    assert result == ["pi_power_status"]


def test_detect_tools_routes_pi_network_status():
    result = tool_manager.detect_tools(
        "Vilket nätverk och vilka IP-adresser har min Raspberry Pi?"
    )
    assert result == ["pi_network_status"]


def test_detect_tools_routes_pi_processes_and_services_together():
    result = tool_manager.detect_tools(
        "Vilka processer och tjänster körs på min Raspberry Pi?"
    )
    assert result == [
        "pi_process_status",
        "pi_services_status",
    ]


def test_detect_tools_routes_pi_system_logs():
    result = tool_manager.detect_tools(
        "Visa systemloggarna på min Raspberry Pi."
    )
    assert result == ["pi_system_logs"]


def test_detect_tools_finds_hardware_inventory():
    result = tool_manager.detect_tools(
        "Vilken hårdvara och vilka anslutna enheter finns?"
    )
    assert result == ["hardware_inventory"]


def test_detect_tools_finds_hardware_changes():
    result = tool_manager.detect_tools(
        "Har någon ny hårdvara anslutits?"
    )
    assert "hardware_changes" in result


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
        object(),
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
