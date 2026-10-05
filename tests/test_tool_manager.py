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


def test_detect_tools_routes_excel_create():
    result = tool_manager.detect_tools(
        'Skapa Excel-filen "budget.xlsx" med kolumner Namn, Belopp.'
    )
    assert result == ["excel_create"]


def test_detect_tools_routes_excel_read():
    result = tool_manager.detect_tools(
        'Läs Excel-filen "budget.xlsx".'
    )
    assert result == ["excel_read"]


def test_detect_tools_routes_excel_append():
    result = tool_manager.detect_tools(
        'Lägg till raden Kaffe, 35 i "budget.xlsx".'
    )
    assert result == ["excel_append"]


def test_detect_tools_routes_excel_set_cell():
    result = tool_manager.detect_tools(
        'Ändra cell B2 i "budget.xlsx" till 40.'
    )
    assert result == ["excel_set_cell"]


def test_detect_tools_routes_excel_sheet_management():
    assert tool_manager.detect_tools(
        'Lista blad i "budget.xlsx".'
    ) == ["excel_list_sheets"]
    assert tool_manager.detect_tools(
        'Skapa blad "Februari" i "budget.xlsx".'
    ) == ["excel_create_sheet"]


def test_detect_tools_routes_workspace_text_files():
    assert tool_manager.detect_tools(
        'Läs filen "notes.txt".'
    ) == ["workspace_read"]
    assert tool_manager.detect_tools(
        'Skapa filen "notes.txt" med innehållet Hej.'
    ) == ["workspace_write"]
    assert tool_manager.detect_tools(
        "Lista workspace."
    ) == ["workspace_list"]


def test_detect_tools_routes_explicit_internet_search():
    result = tool_manager.detect_tools(
        "Sök på internet efter Raspberry Pi 5."
    )
    assert result == ["internet_search"]


def test_detect_tools_routes_explicit_public_page_fetch():
    result = tool_manager.detect_tools(
        "Läs https://example.com/test och sammanfatta sidan."
    )
    assert result == ["web_fetch_text"]


def test_detect_tools_routes_explicit_source_verification():
    result = tool_manager.detect_tools(
        "Granska källan https://example.com/report."
    )
    assert result == ["source_verify_page"]


def test_detect_tools_routes_multi_source_research():
    result = tool_manager.detect_tools(
        "Jämför källor om Raspberry Pi 5 strömförbrukning."
    )
    assert result == ["research_top_three"]


def test_detect_tools_routes_gps_location():
    result = tool_manager.detect_tools(
        "Vilka koordinater har jag enligt GPS?"
    )
    assert result == ["location_status"]


def test_detect_tools_routes_live_vision():
    result = tool_manager.detect_tools(
        "Analysera livekameran."
    )
    assert result == ["vision_analyze_live"]


def test_detect_tools_routes_camera_stream_status():
    result = tool_manager.detect_tools(
        "Testa kamerastreamen."
    )
    assert result == ["camera_stream_status"]


def test_detect_tools_routes_video_analysis():
    result = tool_manager.detect_tools(
        "Analysera videon och beskriv vad som syns."
    )
    assert result == ["vision_analyze_video"]


def test_detect_tools_routes_record_then_video_analysis():
    result = tool_manager.detect_tools(
        "Spela in en video och analysera videon."
    )
    assert result == [
        "camera_record_video",
        "vision_analyze_video",
    ]


def test_detect_tools_routes_video_frame_sampling():
    result = tool_manager.detect_tools(
        "Plocka ut representativa bildrutor ur videon."
    )
    assert result == ["camera_sample_video_frames"]


def test_detect_tools_routes_record_then_sample_video():
    result = tool_manager.detect_tools(
        "Spela in en video och plocka ut bildrutor."
    )
    assert result == [
        "camera_record_video",
        "camera_sample_video_frames",
    ]


def test_detect_tools_routes_video_recording():
    result = tool_manager.detect_tools(
        "Spela in en video med kameran."
    )
    assert result == ["camera_record_video"]


def test_detect_tools_routes_change_detection():
    result = tool_manager.detect_tools(
        "Jämför bilderna och säg vad som har ändrats."
    )
    assert result == ["vision_detect_change"]


def test_detect_tools_routes_capture_then_change_detection():
    result = tool_manager.detect_tools(
        "Ta en bild och jämför med den förra bilden."
    )
    assert result == [
        "camera_capture",
        "vision_detect_change",
    ]


def test_detect_tools_routes_object_detection():
    result = tool_manager.detect_tools(
        "Vilka objekt syns på bilden?"
    )
    assert result == ["vision_detect_objects"]


def test_detect_tools_routes_capture_then_object_detection():
    result = tool_manager.detect_tools(
        "Ta en bild och identifiera objekt."
    )
    assert result == [
        "camera_capture",
        "vision_detect_objects",
    ]


def test_detect_tools_routes_vision_ocr():
    result = tool_manager.detect_tools(
        "Läs texten i bilden."
    )
    assert result == ["vision_read_text"]


def test_detect_tools_routes_capture_then_ocr():
    result = tool_manager.detect_tools(
        "Ta en bild och läs texten i bilden."
    )
    assert result == [
        "camera_capture",
        "vision_read_text",
    ]


def test_detect_tools_routes_vision_analysis():
    result = tool_manager.detect_tools(
        "Vad ser du på bilden?"
    )
    assert result == ["vision_analyze"]


def test_detect_tools_routes_capture_then_vision():
    result = tool_manager.detect_tools(
        "Ta en bild och analysera bilden."
    )
    assert result == [
        "camera_capture",
        "vision_analyze",
    ]


def test_detect_tools_routes_camera_capture():
    result = tool_manager.detect_tools(
        "Ta en bild med kameran."
    )
    assert result == ["camera_capture"]


def test_camera_inventory_is_still_distinct_from_capture():
    result = tool_manager.detect_tools(
        "Vilka kameror är anslutna?"
    )
    assert result == ["camera_status"]


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


def test_detect_tools_routes_ventuno_status_bundle():
    result = tool_manager.detect_tools(
        "Hur mår min Arduino VENTUNO Q, CPU RAM temperatur och disk?"
    )
    assert result == [
        "cpu_status",
        "ram_status",
        "temperature_status",
        "disk_status",
        "geniex_status",
    ]


def test_detect_tools_routes_ventuno_bus_devices():
    result = tool_manager.detect_tools(
        "Vilka I2C-enheter och SPI-enheter finns på min VENTUNO?"
    )
    assert result == [
        "ventuno_bus_devices_status"
    ]


def test_detect_tools_routes_gpio_to_ventuno_safety_not_pi_pinout():
    result = tool_manager.detect_tools(
        "Vilken GPIO ska jag använda för I2C på Arduino VENTUNO Q?"
    )
    assert result == [
        "ventuno_io_safety"
    ]


def test_detect_tools_routes_explicit_gpio_to_ventuno_safety():
    result = tool_manager.detect_tools(
        "Kan jag koppla en 5 V-signal till GPIO17?"
    )
    assert result == [
        "ventuno_io_safety"
    ]


def test_detect_tools_routes_ventuno_interface_inventory():
    result = tool_manager.detect_tools(
        "Vilka gränssnitt och portar finns på min VENTUNO?"
    )
    assert result == [
        "ventuno_interfaces_status"
    ]


def test_detect_tools_routes_ventuno_power_status():
    result = tool_manager.detect_tools(
        "Hur mycket ström drar min VENTUNO i watt?"
    )
    assert result == [
        "ventuno_power_status"
    ]


def test_detect_tools_routes_ventuno_network_status():
    result = tool_manager.detect_tools(
        "Vilket nätverk och vilka IP-adresser har min VENTUNO?"
    )
    assert result == [
        "ventuno_network_status"
    ]


def test_detect_tools_routes_ventuno_processes_and_services_together():
    result = tool_manager.detect_tools(
        "Vilka processer och tjänster körs på min VENTUNO?"
    )
    assert result == [
        "ventuno_process_status",
        "ventuno_services_status",
    ]


def test_detect_tools_routes_ventuno_system_logs():
    result = tool_manager.detect_tools(
        "Visa systemloggarna på min VENTUNO."
    )
    assert result == [
        "ventuno_system_logs"
    ]


def test_detect_tools_routes_npu_to_geniex_status():
    result = tool_manager.detect_tools(
        "Visa NPU accelerator status."
    )
    assert result == [
        "geniex_status"
    ]


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



def test_run_tools_passes_user_input_only_to_query_aware_tool():
    seen = {}

    tools = {
        "internet_search": {
            "function": lambda query: seen.setdefault("query", query) or "ok",
            "description": "search",
            "pass_user_input": True,
        },
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "cpu",
        },
    }

    result = tool_manager.run_tools(
        ["internet_search", "cpu_status"],
        tools,
        user_input="Sök på internet efter test",
    )

    assert seen["query"] == "Sök på internet efter test"
    assert result["cpu_status"] == "CPU OK"


def test_run_tools_reports_missing_user_input_for_query_tool():
    tools = {
        "internet_search": {
            "function": lambda query: query,
            "description": "search",
            "pass_user_input": True,
        }
    }

    result = tool_manager.run_tools(
        ["internet_search"],
        tools,
    )

    assert "kräver användarens fråga" in result["internet_search"]



def test_detect_tools_routes_ventuno_rpc_status():
    result = tool_manager.detect_tools(
        "Visa status för Ventuno RPC."
    )
    assert result == [
        "ventuno_rpc_status"
    ]



def test_detect_tools_routes_ventuno_mcu_status():
    result = tool_manager.detect_tools(
        "Visa STM32 status."
    )
    assert result == [
        "ventuno_mcu_status"
    ]



def test_detect_tools_routes_geniex_status():
    result = tool_manager.detect_tools(
        "Visa GenieX status."
    )
    assert result == [
        "geniex_status"
    ]



def test_detect_tools_routes_myai_health():
    assert tool_manager.detect_tools(
        "Hur mår MyAI?"
    ) == [
        "myai_health_status"
    ]
    assert tool_manager.detect_tools(
        "Visa MyAI status."
    ) == [
        "myai_health_status"
    ]


class FakeErrorLogger:
    def __init__(self):
        self.events = []

    def log_exception(
        self,
        event,
        component,
        error,
    ):
        self.events.append(
            (
                event,
                component,
                type(error).__name__,
                str(error),
            )
        )
        return True


def test_run_tools_logs_failure_and_keeps_other_results():
    logger = FakeErrorLogger()

    def broken():
        raise RuntimeError(
            "sensor unavailable"
        )

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "cpu",
        },
        "temperature_status": {
            "function": broken,
            "description": "temperature",
        },
    }

    result = tool_manager.run_tools(
        [
            "cpu_status",
            "temperature_status",
        ],
        tools,
        error_logger=logger,
    )

    assert result["cpu_status"] == "CPU OK"
    assert "sensor unavailable" in result[
        "temperature_status"
    ]
    assert logger.events == [
        (
            "tool_error",
            "temperature_status",
            "RuntimeError",
            "sensor unavailable",
        )
    ]


def test_run_tools_survives_error_logger_failure():
    class BrokenLogger:
        def log_exception(
            self,
            event,
            component,
            error,
        ):
            raise OSError(
                "log target unavailable"
            )

    def broken():
        raise RuntimeError(
            "tool failed"
        )

    result = tool_manager.run_tools(
        ["ram_status"],
        {
            "ram_status": {
                "function": broken,
                "description": "ram",
            }
        },
        error_logger=BrokenLogger(),
    )

    assert "tool failed" in result[
        "ram_status"
    ]


def test_detect_tools_routes_recent_myai_errors():
    assert tool_manager.detect_tools(
        "Vilka fel har MyAI haft?"
    ) == [
        "myai_recent_errors"
    ]
    assert tool_manager.detect_tools(
        "Visa MyAI fellogg."
    ) == [
        "myai_recent_errors"
    ]


def test_detect_tools_routes_ventuno_stability_report():
    assert tool_manager.detect_tools(
        "Visa VENTUNO stabilitetsrapport."
    ) == [
        "ventuno_stability_report"
    ]
    assert tool_manager.detect_tools(
        "Analysera 72-timmarstestet."
    ) == [
        "ventuno_stability_report"
    ]


def test_detect_tools_routes_myai_audit_status():
    assert tool_manager.detect_tools(
        "Visa auditloggen."
    ) == [
        "myai_audit_status"
    ]
    assert tool_manager.detect_tools(
        "Vilka ändringar har MyAI gjort?"
    ) == [
        "myai_audit_status"
    ]


def test_detect_tools_routes_combined_myai_diagnostics():
    assert tool_manager.detect_tools(
        "Gör en MyAI diagnostik."
    ) == [
        "myai_diagnostic_report"
    ]
    assert tool_manager.detect_tools(
        "Visa samlad diagnostik."
    ) == [
        "myai_diagnostic_report"
    ]


def test_detect_tools_routes_sweden_shopping_comparison():
    assert tool_manager.detect_tools(
        "Jämför pris på Widget Pro."
    ) == [
        "shopping_compare_sweden"
    ]
    assert tool_manager.detect_tools(
        "Hitta billigaste Widget Pro."
    ) == [
        "shopping_compare_sweden"
    ]


def test_detect_tools_routes_weather_requests():
    assert tool_manager.detect_tools(
        "Vad blir det för väder i Stockholm idag?"
    ) == [
        "weather_forecast"
    ]
    assert tool_manager.detect_tools(
        "Vad blir det för väder idag?"
    ) == [
        "weather_forecast"
    ]
    assert tool_manager.detect_tools(
        "Weather in London tomorrow"
    ) == [
        "weather_forecast"
    ]


def test_detect_tools_routes_memory_administration_status():
    assert tool_manager.detect_tools(
        "Visa minnen som behöver granskas."
    ) == [
        "memory_review_status"
    ]
    assert tool_manager.detect_tools(
        "Visa minneskonflikter."
    ) == [
        "memory_review_status"
    ]
    assert tool_manager.detect_tools(
        "Visa gamla minnen."
    ) == [
        "memory_review_status"
    ]


def test_detect_tools_routes_memory_administration_actions():
    assert tool_manager.detect_tools(
        "GODKÄNN MINNESGRANSKNING 3"
    ) == [
        "memory_review_action"
    ]
    assert tool_manager.detect_tools(
        "RADERA MINNE 7"
    ) == [
        "memory_review_action"
    ]
