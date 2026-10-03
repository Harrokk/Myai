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


def run_tools(tool_names, tools):
    """Kör flera verktyg och samla varje resultat separat."""
    results = {}

    for tool_name in tool_names:
        if tool_name not in tools:
            continue

        try:
            tool_function = tools[tool_name]["function"]
            results[tool_name] = tool_function()
        except Exception as error:
            results[tool_name] = (
                f"Fel vid körning av {tool_name}: {error}"
            )

    return results
