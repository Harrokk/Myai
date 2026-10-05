import importlib
import pkgutil

import modules

from core.intermediate_results import (
    dependent_visual_research,
)
from core.orchestration import (
    build_safe_orchestration_plan,
    is_orchestration_safe_tool,
)


STATUS_WORDS = [
    "hur mycket",
    "hur många",
    "hur varm",
    "hur varmt",
    "hur arbetar",
    "hur jobbar",
    "använder",
    "används",
    "belastning",
    "status",
    "temperatur",
    "ledig",
    "ledigt",
    "utrymme",
    "plats",
    "vilka",
    "ansluten",
    "anslutna",
    "anslutits",
    "inkopplad",
    "inkopplade",
    "ny",
    "nya",
]

BLUETOOTH_PROXIMITY_WORDS = [
    "rssi",
    "avstånd",
    "hur långt",
    "nära",
    "närhet",
    "närmast",
]


TOOL_KEYWORDS = {
    "myai_health_status": [
        "myai status",
        "myai hälsa",
        "myai health",
        "systemhälsa",
        "ai hälsa",
    ],
    "gpu_status": [
        "gpu",
        "grafikkort",
        "grafikkortet",
        "grafik",
        "vram",
        "grafikkortsminne",
        "nvidia",
        "rtx",
    ],
    "cpu_status": [
        "cpu",
        "processor",
        "processorn",
    ],
    "ram_status": [
        "ram",
        "arbetsminne",
        "ram-minne",
        "ramminne",
        "minnesanvändning",
        "minnes användning",
    ],
    "temperature_status": [
        "temperatur",
        "temperaturer",
        "värme",
        "varm",
        "varmt",
        "överhett",
        "överhettad",
    ],
    "disk_status": [
        "disk",
        "hårddisk",
        "ssd",
        "lagring",
        "lagringsutrymme",
        "ledigt utrymme",
        "diskutrymme",
        "disk utrymme",
    ],
    "usb_status": [
        "usb",
        "usb-enhet",
        "usb-enheter",
        "usb enhet",
        "usb enheter",
    ],
    "camera_status": [
        "kamera",
        "kameror",
        "webbkamera",
        "webbkameror",
        "videoenhet",
        "videoenheter",
    ],
    "bluetooth_status": [
        "bluetooth",
        "blåtand",
        "bluetooth-enhet",
        "bluetooth-enheter",
        "bluetooth enhet",
        "bluetooth enheter",
    ],
    "hardware_inventory": [
        "hårdvara",
        "hardware",
        "alla enheter",
        "anslutna enheter",
        "inkopplade enheter",
    ],
    "geniex_status": [
        "geniex status",
        "geniex hälsa",
        "geniex health",
        "ai backend status",
        "llm backend status",
    ],
    "ventuno_mcu_status": [
        "ventuno mcu",
        "stm32 status",
        "mcu status",
        "stm32 diagnostik",
        "mcu diagnostik",
    ],
    "ventuno_rpc_status": [
        "ventuno rpc",
        "stm32 rpc",
        "arduino router",
        "ventuno brygga",
        "ventuno bridge",
    ],
    "hardware_changes": [
        "ny hårdvara",
        "nya enheter",
        "ny enhet",
        "hårdvaruförändring",
        "hårdvaruförändringar",
        "något anslutits",
        "något kopplats in",
    ],
}




def _log_error(
    error_logger,
    event,
    component,
    error,
):
    if error_logger is None:
        return False

    try:
        return bool(
            error_logger.log_exception(
                event,
                component,
                error,
            )
        )
    except Exception:
        return False

def load_tools(error_logger=None):
    """Ladda alla TOOLS-register från moduler under paketet modules."""
    tools = {}

    for module_info in pkgutil.walk_packages(
        modules.__path__,
        modules.__name__ + ".",
    ):
        module_name = module_info.name

        try:
            module = importlib.import_module(module_name)
            module_tools = getattr(module, "TOOLS", None)

            if isinstance(module_tools, dict):
                tools.update(module_tools)

        except Exception as error:
            _log_error(
                error_logger,
                "module_load_error",
                module_name,
                error,
            )

            print(
                f"Varning: kunde inte ladda modulen "
                f"{module_name}: {error}"
            )

    return tools


def detect_tools(user_input):
    """Snabb regelbaserad identifiering för vanliga lokala statusfrågor."""
    text = user_input.lower().strip()

    asks_myai_health = any(
        phrase in text
        for phrase in (
            "hur mår myai",
            "hur mår du",
            "myai status",
            "myai hälsa",
            "myai health",
            "systemhälsa",
            "ai hälsa",
        )
    )

    if asks_myai_health:
        return [
            "myai_health_status"
        ]

    asks_myai_errors = any(
        phrase in text
        for phrase in (
            "vilka fel har myai haft",
            "har myai haft några fel",
            "senaste myai-fel",
            "senaste myai fel",
            "senaste fel",
            "myai fellogg",
            "myai felhistorik",
            "myai error log",
            "recent myai errors",
        )
    )

    if asks_myai_errors:
        return [
            "myai_recent_errors"
        ]

    asks_myai_audit = any(
        phrase in text
        for phrase in (
            "visa auditloggen",
            "visa audit loggen",
            "myai audit",
            "audit-logg",
            "audit log",
            "senaste skrivåtgärder",
            "vilka ändringar har myai gjort",
            "myai action log",
        )
    )

    if asks_myai_audit:
        return [
            "myai_audit_status"
        ]

    asks_myai_diagnostics = any(
        phrase in text
        for phrase in (
            "kör myai diagnostik",
            "gör en myai diagnostik",
            "gör myai diagnostik",
            "samlad diagnostik",
            "myai diagnostikrapport",
            "myai diagnostik",
            "systemdiagnostik",
            "diagnostic report",
            "myai diagnostics",
        )
    )

    if asks_myai_diagnostics:
        return [
            "myai_diagnostic_report"
        ]

    asks_memory_admin_action = any(
        phrase in text
        for phrase in (
            "godkänn minnesgranskning",
            "avvisa minnesgranskning",
            "ersätt minne ",
            "radera minne ",
        )
    )

    if asks_memory_admin_action:
        return [
            "memory_review_action"
        ]

    asks_memory_admin_status = any(
        phrase in text
        for phrase in (
            "visa minnen som behöver granskas",
            "visa minnesgranskningar",
            "väntande minnesgranskningar",
            "minneskonflikter",
            "konflikter i minnet",
            "visa gamla minnen",
            "gamla minnen",
            "minneshistorik",
            "memory reviews",
            "memory conflicts",
            "old memories",
            "memory history",
        )
    )

    if asks_memory_admin_status:
        return [
            "memory_review_status"
        ]

    asks_ventuno_stability = any(
        phrase in text
        for phrase in (
            "ventuno stabilitetsrapport",
            "ventuno stabilitet",
            "stabilitetsrapport",
            "analysera stabilitetsloggen",
            "analysera 72-timmarstestet",
            "analysera 72 timmarstestet",
            "72-timmarsrapport",
            "72 timmars rapport",
            "ventuno stability report",
        )
    )

    if asks_ventuno_stability:
        return [
            "ventuno_stability_report"
        ]

    mentions_xlsx = ".xlsx" in text

    if mentions_xlsx:
        if any(
            phrase in text
            for phrase in (
                "lista blad",
                "visa blad",
                "vilka blad",
                "list sheets",
            )
        ):
            return ["excel_list_sheets"]

        if any(
            phrase in text
            for phrase in (
                "skapa blad",
                "skapa nytt blad",
                "create sheet",
            )
        ):
            return ["excel_create_sheet"]

        if any(
            phrase in text
            for phrase in (
                "sätt ",
                "ändra cell",
                "skriv ",
                "set cell",
            )
        ) and any(
            token in text
            for token in ("cell", " a1", " b1", " a2", " b2", " c")
        ):
            return ["excel_set_cell"]

        if any(
            phrase in text
            for phrase in (
                "lägg till raden",
                "lägg till rad",
                "addera raden",
                "append row",
            )
        ):
            return ["excel_append"]

        if any(
            phrase in text
            for phrase in (
                "skapa excel",
                "skapa excel-filen",
                "skapa excel fil",
                "create excel",
                "create workbook",
            )
        ):
            return ["excel_create"]

        if any(
            phrase in text
            for phrase in (
                "läs excel",
                "läs excel-filen",
                "visa excel",
                "read excel",
                "read workbook",
            )
        ):
            return ["excel_read"]

    mentions_text_file = any(
        extension in text
        for extension in (".txt", ".md", ".csv", ".json")
    )

    if mentions_text_file:
        if any(
            phrase in text
            for phrase in (
                "skapa fil",
                "skriv fil",
                "skriv till",
                "spara i",
                "create file",
                "write file",
            )
        ):
            return ["workspace_write"]

        if any(
            phrase in text
            for phrase in (
                "läs fil",
                "visa fil",
                "öppna fil",
                "read file",
            )
        ):
            return ["workspace_read"]

    if any(
        phrase in text
        for phrase in (
            "lista workspace",
            "visa workspace",
            "vilka filer finns i workspace",
            "list workspace",
        )
    ):
        return ["workspace_list"]

    asks_weather = any(
        phrase in text
        for phrase in (
            "väder i ",
            "vädret i ",
            "väder idag",
            "vädret idag",
            "väder i dag",
            "vädret i dag",
            "väder imorgon",
            "vädret imorgon",
            "väder i morgon",
            "vädret i morgon",
            "väderprognos",
            "prognos för ",
            "weather in ",
            "weather today",
            "weather tomorrow",
            "weather forecast",
            "forecast for ",
        )
    )

    if asks_weather:
        return [
            "weather_forecast"
        ]

    asks_shopping_compare = any(
        phrase in text
        for phrase in (
            "jämför pris på ",
            "jämför priser på ",
            "prisjämför ",
            "hitta billigaste ",
            "hitta bästa pris på ",
            "sök pris på ",
            "compare price for ",
            "compare prices for ",
            "find cheapest ",
            "find best price for ",
        )
    )

    if asks_shopping_compare:
        return [
            "shopping_compare_sweden"
        ]

    asks_research = any(
        phrase in text
        for phrase in (
            "researcha ",
            "gör research om ",
            "undersök källor",
            "jämför källor om ",
            "verifiera information om ",
            "deep research",
        )
    )

    if asks_research:
        return ["research_top_three"]

    asks_source_verification = (
        ("http://" in text or "https://" in text)
        and any(
            phrase in text
            for phrase in (
                "verifiera källan",
                "verifiera sidan",
                "granska källan",
                "källgranska",
                "bedöm källan",
                "kontrollera källan",
                "verify source",
                "check source",
            )
        )
    )

    if asks_source_verification:
        return ["source_verify_page"]

    asks_page_fetch = (
        ("http://" in text or "https://" in text)
        and any(
            phrase in text
            for phrase in (
                "hämta ",
                "läs ",
                "öppna ",
                "kontrollera ",
                "sammanfatta ",
                "fetch ",
                "read ",
                "open ",
                "summarize ",
            )
        )
    )

    if asks_page_fetch:
        return ["web_fetch_text"]

    asks_internet_search = any(
        phrase in text
        for phrase in (
            "sök på internet",
            "sök på webben",
            "sök internet",
            "webbsök",
            "search the web",
            "search internet",
        )
    )

    if asks_internet_search:
        return ["internet_search"]

    asks_location = any(
        phrase in text
        for phrase in (
            "var är jag",
            "min position",
            "gps position",
            "gps-position",
            "mina koordinater",
            "vilka koordinater",
            "aktuell position",
            "current location",
            "gps coordinates",
        )
    )

    if asks_location:
        return ["location_status"]

    asks_live_vision = any(
        phrase in text
        for phrase in (
            "analysera livekameran",
            "analysera kamerastreamen",
            "vad ser kameran live",
            "vad ser du live",
            "live vision",
            "live-vision",
            "analyze live camera",
        )
    )

    if asks_live_vision:
        return ["vision_analyze_live"]

    asks_camera_stream = any(
        phrase in text
        for phrase in (
            "testa kamerastream",
            "testa kamerastreamen",
            "kontrollera kamerastream",
            "kamerastream status",
            "testa livekamera",
            "kontrollera livekamera",
            "camera stream test",
            "test camera stream",
        )
    )

    if asks_camera_stream:
        return ["camera_stream_status"]

    asks_video_recording = any(
        phrase in text
        for phrase in (
            "spela in video",
            "spela in en video",
            "filma",
            "ta en video",
            "ta ett videoklipp",
            "record video",
            "record a video",
        )
    )
    asks_video_analysis = any(
        phrase in text
        for phrase in (
            "analysera videon",
            "analysera video",
            "beskriv videon",
            "sammanfatta videon",
            "vad ser du i videon",
            "vad händer i videon",
            "analyze video",
            "describe video",
            "summarize video",
        )
    )

    asks_video_sampling = any(
        phrase in text
        for phrase in (
            "plocka ut bildrutor",
            "plocka bildrutor",
            "representativa bildrutor",
            "sampla videon",
            "sampla video",
            "bildrutor ur videon",
            "extract video frames",
            "sample video frames",
        )
    )

    if asks_video_recording and asks_video_analysis:
        return [
            "camera_record_video",
            "vision_analyze_video",
        ]

    if asks_video_analysis:
        return ["vision_analyze_video"]

    if asks_video_recording and asks_video_sampling:
        return [
            "camera_record_video",
            "camera_sample_video_frames",
        ]

    if asks_video_recording:
        return ["camera_record_video"]

    if asks_video_sampling:
        return ["camera_sample_video_frames"]

    asks_camera_capture = any(
        phrase in text
        for phrase in (
            "ta en bild",
            "ta bild",
            "ta ett foto",
            "ta foto",
            "fotografera",
            "capture image",
            "capture photo",
        )
    )
    asks_change_detection = any(
        phrase in text
        for phrase in (
            "vad har ändrats",
            "vad har förändrats",
            "jämför bilderna",
            "jämför med förra bilden",
            "jämför med den förra",
            "förändring i miljön",
            "förändrats i bilden",
            "compare images",
            "what changed",
        )
    )

    asks_object_detection = any(
        phrase in text
        for phrase in (
            "identifiera objekt",
            "vilka objekt",
            "vilka saker",
            "vad finns för objekt",
            "hitta objekt",
            "object detection",
            "detect objects",
        )
    )

    asks_ocr = any(
        phrase in text
        for phrase in (
            "läs texten",
            "läs text i bilden",
            "läs texten i bilden",
            "vad står det",
            "vad står på bilden",
            "ocr",
            "transkribera bilden",
            "extract text",
            "read text",
        )
    )

    asks_vision_analysis = any(
        phrase in text
        for phrase in (
            "vad ser du",
            "analysera bilden",
            "analysera bild",
            "analysera fotot",
            "beskriv bilden",
            "vad finns på bilden",
            "vad är på bilden",
            "analyze image",
            "describe image",
        )
    )

    if asks_camera_capture and asks_change_detection:
        return ["camera_capture", "vision_detect_change"]

    if asks_change_detection:
        return ["vision_detect_change"]

    if asks_camera_capture and asks_object_detection:
        return ["camera_capture", "vision_detect_objects"]

    if asks_object_detection:
        return ["vision_detect_objects"]

    if asks_camera_capture and asks_ocr:
        return ["camera_capture", "vision_read_text"]

    if asks_ocr:
        return ["vision_read_text"]

    if asks_camera_capture and asks_vision_analysis:
        return ["camera_capture", "vision_analyze"]

    if asks_camera_capture:
        return ["camera_capture"]

    if asks_vision_analysis:
        return ["vision_analyze"]

    mentions_ventuno = any(
        word in text
        for word in (
            "ventuno",
            "arduino ventuno",
            "dragonwing",
            "qcs8275",
            "qualcomm",
        )
    )

    asks_accelerator = any(
        phrase in text
        for phrase in (
            "npu",
            "hexagon",
            "ai accelerator",
            "ai-accelerator",
            "accelerator status",
        )
    )

    if asks_accelerator:
        return [
            "ventuno_accelerator_status"
        ]

    ventuno_diagnostic_tools = []

    if mentions_ventuno:
        if any(
            word in text
            for word in (
                "nätverk",
                "nätverks",
                "ip-adress",
                "ip adress",
                "ethernet",
                "wifi",
                "wi-fi",
            )
        ):
            ventuno_diagnostic_tools.append(
                "ventuno_network_status"
            )

        if any(
            word in text
            for word in (
                "processer",
                "processlista",
                "process list",
                "vilka processer",
            )
        ):
            ventuno_diagnostic_tools.append(
                "ventuno_process_status"
            )

        if any(
            word in text
            for word in (
                "tjänster",
                "service",
                "services",
                "systemd",
            )
        ):
            ventuno_diagnostic_tools.append(
                "ventuno_services_status"
            )

        if any(
            word in text
            for word in (
                "systemlogg",
                "systemloggar",
                "loggar",
                "journalctl",
                "journal",
            )
        ):
            ventuno_diagnostic_tools.append(
                "ventuno_system_logs"
            )

    if ventuno_diagnostic_tools:
        return ventuno_diagnostic_tools

    asks_ventuno_power = any(
        word in text
        for word in (
            "strömförbrukning",
            "ström",
            "effekt",
            "watt",
            "ampere",
            "power draw",
        )
    )

    if mentions_ventuno and asks_ventuno_power:
        return [
            "ventuno_power_status"
        ]

    asks_ventuno_status = any(
        word in text
        for word in (
            "status",
            "temperatur",
            "varm",
            "cpu",
            "ram",
            "lagring",
            "disk",
            "hur mår",
        )
    )

    if mentions_ventuno and asks_ventuno_status:
        return [
            "cpu_status",
            "ram_status",
            "temperature_status",
            "disk_status",
            "geniex_status",
        ]

    asks_bus_devices = any(
        phrase in text
        for phrase in (
            "i2c-enheter",
            "i2c enheter",
            "spi-enheter",
            "spi enheter",
            "anslutna sensorer",
            "sensorer på i2c",
            "sensorer på spi",
            "bussenheter",
            "bus devices",
        )
    )

    if asks_bus_devices:
        return [
            "ventuno_bus_devices_status"
        ]

    asks_ventuno_interfaces = any(
        phrase in text
        for phrase in (
            "vilka gränssnitt",
            "vilka portar",
            "tillgängliga gränssnitt",
            "tillgängliga portar",
            "gpiochip",
            "spidev",
            "i2c-",
            "ttyhs",
            "ttyama",
        )
    )

    if asks_ventuno_interfaces:
        return [
            "ventuno_interfaces_status"
        ]

    asks_io_reference = any(
        word in text
        for word in (
            "gpio",
            "i2c",
            "spi",
            "uart",
            "pinout",
            "vilken pin",
            "vilken pinne",
            "koppla in",
            "inkoppling",
        )
    )

    if asks_io_reference:
        return [
            "ventuno_io_safety"
        ]

    mentions_bluetooth = any(
        word in text
        for word in ("bluetooth", "blåtand")
    )
    asks_proximity = any(
        word in text
        for word in BLUETOOTH_PROXIMITY_WORDS
    )

    if mentions_bluetooth and asks_proximity:
        return ["bluetooth_nearby"]

    if not any(word in text for word in STATUS_WORDS):
        return []

    detected_tools = []

    for tool_name, keywords in TOOL_KEYWORDS.items():
        if any(word in text for word in keywords):
            detected_tools.append(tool_name)

    return detected_tools


def ai_detect_tools(user_input, tools, llm_client):
    """Låt den lokala modellen välja ett eller flera verktyg."""
    tool_list = "\n".join(
        f"- {name}: {tool['description']}"
        for name, tool in tools.items()
    )

    prompt = f"""
Du är verktygsidentifierare för MyAI.

Din uppgift är att avgöra vilka av de tillgängliga verktygen
som behövs för att besvara användarens fråga.

Flera verktyg kan behövas samtidigt.

Tillgängliga verktyg:

{tool_list}

Användaren frågar:

{user_input}

Svara ENDAST med verktygsnamnen separerade med kommatecken.

Exempel:
gpu_status,cpu_status,ram_status

Om inget verktyg behövs:
none
"""

    result = llm_client.chat(
        [
            {
                "role": "system",
                "content": prompt,
            }
        ],
        timeout=120,
    ).strip().lower()

    if result == "none":
        return []

    detected_tools = []

    for item in result.split(","):
        tool_name = item.strip()

        if tool_name in tools and tool_name not in detected_tools:
            detected_tools.append(tool_name)

    return detected_tools


def _direct_plan(
    user_input,
    tool_names,
    *,
    source,
):
    return {
        "enabled": True,
        "orchestrated": False,
        "source": source,
        "steps": [
            {
                "tool": tool_name,
                "input": user_input,
                "effect": "direct",
            }
            for tool_name in tool_names
        ],
        "blocked_tools": [],
        "truncated": False,
    }


def select_tool_plan(
    user_input,
    tools,
    llm_client,
    settings=None,
):
    """Välj en säker exekveringsplan med befintlig direkt/LLM-routing som fallback."""

    direct = [
        tool_name
        for tool_name in (
            detect_tools(
                user_input
            )
            or []
        )
        if tool_name in tools
    ]

    if (
        direct
        and settings is not None
        and any(
            not is_orchestration_safe_tool(
                tool_name,
                user_input=user_input,
                settings=settings,
            )
            for tool_name in direct
        )
    ):
        return _direct_plan(
            user_input,
            direct,
            source="direct_non_orchestrated",
        )

    if settings is not None:
        planned = build_safe_orchestration_plan(
            user_input,
            available_tools=tools,
            detect_function=detect_tools,
            settings=settings,
        )

        if planned.get(
            "orchestrated",
            False,
        ):
            return planned

        if dependent_visual_research(
            user_input
        ):
            return {
                "enabled": True,
                "orchestrated": False,
                "source": (
                    "dependent_visual_research_requires_intermediate"
                ),
                "steps": [],
                "deferred_steps": [],
                "blocked_tools": [],
                "truncated": False,
            }

    if direct:
        return _direct_plan(
            user_input,
            direct,
            source="direct",
        )

    fallback_tools = tools
    fallback_source = "llm_fallback"

    if settings is not None and settings.get(
        "orchestration",
        {},
    ).get(
        "enabled",
        True,
    ):
        fallback_tools = {
            name: tool
            for name, tool in tools.items()
            if is_orchestration_safe_tool(
                name,
                user_input=user_input,
                settings=settings,
            )
        }
        fallback_source = (
            "llm_safe_fallback"
        )

    tools_to_run = ai_detect_tools(
        user_input,
        fallback_tools,
        llm_client,
    )
    selected = [
        tool_name
        for tool_name in tools_to_run
        if tool_name in fallback_tools
    ]
    return _direct_plan(
        user_input,
        selected,
        source=fallback_source,
    )


def select_tools(
    user_input,
    tools,
    llm_client,
    settings=None,
):
    """Bakåtkompatibel lista över verktyg från den strukturerade planen."""

    plan = select_tool_plan(
        user_input,
        tools,
        llm_client,
        settings=settings,
    )
    return [
        step[
            "tool"
        ]
        for step in plan.get(
            "steps",
            []
        )
    ]


def _bounded_tool_result(
    value,
    limit,
):
    if limit is None:
        return value

    try:
        maximum = int(
            limit
        )
    except (
        TypeError,
        ValueError,
    ):
        return value

    if maximum <= 0:
        return value

    if not isinstance(
        value,
        str,
    ):
        return value

    if len(
        value
    ) <= maximum:
        return value

    suffix = (
        "\n...[verktygsresultat trunkerat]"
    )
    keep = max(
        0,
        maximum
        - len(
            suffix
        ),
    )
    return (
        value[
            :keep
        ]
        + suffix
    )


def run_tools(
    tool_names,
    tools,
    user_input=None,
    error_logger=None,
    tool_inputs=None,
    result_char_limit=None,
):
    """Kör flera verktyg sekventiellt och samla varje resultat separat."""

    results = {}
    per_tool_input = (
        tool_inputs
        if isinstance(
            tool_inputs,
            dict,
        )
        else {}
    )

    for tool_name in tool_names:
        if tool_name not in tools:
            continue

        try:
            tool = tools[tool_name]
            tool_function = tool["function"]

            if tool.get("pass_user_input", False):
                effective_input = per_tool_input.get(
                    tool_name,
                    user_input,
                )

                if effective_input is None:
                    raise ValueError(
                        f"{tool_name} kräver användarens fråga som indata."
                    )

                result = tool_function(
                    effective_input
                )
            else:
                result = tool_function()

            results[
                tool_name
            ] = _bounded_tool_result(
                result,
                result_char_limit,
            )
        except Exception as error:
            _log_error(
                error_logger,
                "tool_error",
                tool_name,
                error,
            )

            results[tool_name] = (
                f"Fel vid körning av {tool_name}: {error}"
            )

    return results
