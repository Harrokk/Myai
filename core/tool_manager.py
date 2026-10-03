import importlib
import pkgutil

import modules


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


def load_tools():
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
            print(
                f"Varning: kunde inte ladda modulen "
                f"{module_name}: {error}"
            )

    return tools


def detect_tools(user_input):
    """Snabb regelbaserad identifiering för vanliga lokala statusfrågor."""
    text = user_input.lower().strip()

    asks_excel_append = any(
        phrase in text
        for phrase in (
            "lägg till raden",
            "lägg till rad",
            "addera raden",
            "append row",
        )
    ) and ("excel" in text or ".xlsx" in text)

    asks_excel_create = any(
        phrase in text
        for phrase in (
            "skapa excel",
            "skapa en excel",
            "skapa excel-fil",
            "skapa excel fil",
            "skapa kalkylblad",
            "create excel",
        )
    )

    asks_excel_read = any(
        phrase in text
        for phrase in (
            "läs excel",
            "öppna excel",
            "visa excel",
            "läs kalkylblad",
            "read excel",
        )
    )

    if asks_excel_append:
        return ["excel_append"]

    if asks_excel_create:
        return ["excel_create"]

    if asks_excel_read:
        return ["excel_read"]

    asks_workspace_write = any(
        phrase in text
        for phrase in (
            "skapa fil",
            "skapa en fil",
            "skriv fil",
            "skriv en fil",
            "spara fil",
            "spara en fil",
        )
    )
    asks_workspace_read = any(
        phrase in text
        for phrase in (
            "läs fil",
            "läs filen",
            "öppna fil",
            "öppna filen",
            "visa innehållet i fil",
        )
    )
    asks_workspace_list = any(
        phrase in text
        for phrase in (
            "lista filer",
            "visa filer",
            "vilka filer",
            "filer i workspace",
            "workspace filer",
        )
    )

    if asks_workspace_write:
        return ["workspace_write"]

    if asks_workspace_read:
        return ["workspace_read"]

    if asks_workspace_list:
        return ["workspace_list"]

    asks_gps_refresh = any(
        phrase in text
        for phrase in (
            "uppdatera gps",
            "uppdatera gps-position",
            "uppdatera gps position",
            "hämta gps-position",
            "hämta gps position",
            "läs gps",
            "läs av gps",
            "refresh gps",
            "get gps fix",
        )
    )

    if asks_gps_refresh:
        return ["gps_refresh_location"]

    asks_location_status = any(
        phrase in text
        for phrase in (
            "var är du",
            "var befinner du dig",
            "vilken position",
            "din position",
            "gps-status",
            "gps status",
            "gps-position",
            "gps position",
            "location status",
            "where are you",
        )
    )

    if asks_location_status:
        return ["location_status"]

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
    asks_video_analysis = (
        any(
            phrase in text
            for phrase in (
                "analysera videon",
                "analysera video",
                "analysera senaste videon",
                "analysera den senaste videon",
                "beskriv videon",
                "vad händer i videon",
                "vad syns i videon",
                "analyze video",
                "describe video",
            )
        )
        or ("analysera" in text and "video" in text)
        or ("beskriv" in text and "video" in text)
    )

    if asks_video_recording and asks_video_analysis:
        return [
            "camera_record_video",
            "camera_sample_video_frames",
            "vision_analyze_video",
        ]

    if asks_video_sampling and asks_video_analysis:
        return [
            "camera_sample_video_frames",
            "vision_analyze_video",
        ]

    if asks_video_analysis:
        return [
            "camera_sample_video_frames",
            "vision_analyze_video",
        ]

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

    mentions_pi = any(
        word in text
        for word in ("raspberry pi", "raspberrypi", "pi 5", "pi5")
    )

    pi_diagnostic_tools = []

    if mentions_pi:
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
            pi_diagnostic_tools.append("pi_network_status")

        if any(
            word in text
            for word in (
                "processer",
                "processlista",
                "process list",
                "vilka processer",
            )
        ):
            pi_diagnostic_tools.append("pi_process_status")

        if any(
            word in text
            for word in (
                "tjänster",
                "service",
                "services",
                "systemd",
            )
        ):
            pi_diagnostic_tools.append("pi_services_status")

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
            pi_diagnostic_tools.append("pi_system_logs")

    if pi_diagnostic_tools:
        return pi_diagnostic_tools
    asks_pi_power = any(
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

    if mentions_pi and asks_pi_power:
        return ["pi_power_status"]

    asks_pi_status = any(
        word in text
        for word in (
            "status",
            "temperatur",
            "varm",
            "cpu",
            "ram",
            "lagring",
            "disk",
            "spänning",
            "ström",
            "throttl",
            "underspänning",
            "hur mår",
        )
    )

    if mentions_pi and asks_pi_status:
        return ["pi_system_status"]

    asks_pi_bus_devices = any(
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

    if mentions_pi and asks_pi_bus_devices:
        return ["pi_bus_devices_status"]

    asks_gpio_reference = any(
        word in text
        for word in (
            "gpio",
            "i2c",
            "spi",
            "uart",
            "3,3 v",
            "3.3 v",
            "5 v",
            "5v",
            "pinout",
        )
    )

    if asks_gpio_reference and (
        mentions_pi
        or any(word in text for word in ("gpio", "i2c", "spi", "uart", "pinout"))
    ):
        return ["pi_gpio_reference"]

    asks_pi_interfaces = any(
        phrase in text
        for phrase in (
            "vilka gränssnitt",
            "vilka portar",
            "tillgängliga gränssnitt",
            "tillgängliga portar",
            "gpiochip",
            "spidev",
            "i2c-",
            "ttyama",
        )
    )

    if mentions_pi and asks_pi_interfaces:
        return ["pi_interfaces_status"]

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


def select_tools(user_input, tools, llm_client):
    """Välj verktyg: snabb lokal regel först, LLM som fallback."""
    tools_to_run = detect_tools(user_input)

    if not tools_to_run:
        tools_to_run = ai_detect_tools(
            user_input,
            tools,
            llm_client,
        )

    return [
        tool_name
        for tool_name in tools_to_run
        if tool_name in tools
    ]


def run_tools(tool_names, tools, user_input=None):
    """Kör flera verktyg och samla varje resultat separat.

    Befintliga verktyg utan input_mode körs utan argument.
    Verktyg med input_mode="user_text" får hela användarens instruktion.
    """
    results = {}

    for tool_name in tool_names:
        if tool_name not in tools:
            continue

        try:
            tool = tools[tool_name]
            tool_function = tool["function"]
            input_mode = tool.get("input_mode", "none")

            if input_mode in (None, "", "none"):
                result = tool_function()
            elif input_mode == "user_text":
                if not isinstance(user_input, str):
                    raise ValueError(
                        "verktyget kräver användarens text som indata"
                    )
                result = tool_function(user_input)
            else:
                raise ValueError(
                    f"okänt input_mode: {input_mode}"
                )

            results[tool_name] = result
        except Exception as error:
            results[tool_name] = (
                f"Fel vid körning av {tool_name}: {error}"
            )

    return results
