import importlib
import json
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
    asks_vision_text = any(
        phrase in text
        for phrase in (
            "läs texten i bilden",
            "läs text i bilden",
            "vad står det på bilden",
            "vad står på bilden",
            "ocr",
            "read text in image",
            "read image text",
        )
    )
    asks_vision_objects = any(
        phrase in text
        for phrase in (
            "identifiera objekt",
            "vilka objekt",
            "objekt i bilden",
            "vilka saker finns på bilden",
            "detect objects",
            "objects in image",
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

    if asks_camera_capture and asks_vision_text:
        return ["camera_capture", "vision_read_text"]

    if asks_camera_capture and asks_vision_objects:
        return ["camera_capture", "vision_detect_objects"]

    if asks_camera_capture and asks_vision_analysis:
        return ["camera_capture", "vision_analyze"]

    if asks_vision_text:
        return ["vision_read_text"]

    if asks_vision_objects:
        return ["vision_detect_objects"]

    if asks_camera_capture:
        return ["camera_capture"]

    if asks_vision_analysis:
        return ["vision_analyze"]

    asks_gps_position = any(
        phrase in text
        for phrase in (
            "gps",
            "min position",
            "aktuell position",
            "mina koordinater",
            "vilka koordinater",
            "latitud",
            "longitud",
            "var befinner jag mig",
            "where am i",
        )
    )

    if asks_gps_position:
        return ["gps_status"]

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


def _strip_json_fence(text):
    value = (text or "").strip()

    if value.startswith("```"):
        lines = value.splitlines()

        if lines:
            lines = lines[1:]

        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]

        value = "\n".join(lines).strip()

    return value


def _matches_schema_type(value, expected_type):
    if expected_type == "string":
        return isinstance(value, str)
    if expected_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected_type == "number":
        return (
            isinstance(value, (int, float))
            and not isinstance(value, bool)
        )
    if expected_type == "boolean":
        return isinstance(value, bool)
    if expected_type == "array":
        return isinstance(value, list)
    if expected_type == "object":
        return isinstance(value, dict)
    return True


def validate_tool_arguments(tool_name, arguments, tools):
    if not isinstance(arguments, dict):
        raise ValueError(
            f"Argument för {tool_name} måste vara ett JSON-objekt."
        )

    schema = tools.get(tool_name, {}).get("parameters")

    if not schema:
        if arguments:
            raise ValueError(
                f"{tool_name} tar inga argument."
            )
        return arguments

    properties = schema.get("properties", {})
    required = schema.get("required", [])

    for key in required:
        if key not in arguments:
            raise ValueError(
                f"{tool_name} saknar obligatoriskt argument: {key}"
            )

    if schema.get("additionalProperties") is False:
        unknown = [
            key
            for key in arguments
            if key not in properties
        ]

        if unknown:
            raise ValueError(
                f"{tool_name} fick okända argument: "
                + ", ".join(unknown)
            )

    for key, value in arguments.items():
        definition = properties.get(key, {})
        expected_type = definition.get("type")

        if expected_type and not _matches_schema_type(
            value,
            expected_type,
        ):
            raise ValueError(
                f"{tool_name}.{key} har fel typ; "
                f"förväntade {expected_type}."
            )

        if (
            "enum" in definition
            and value not in definition["enum"]
        ):
            raise ValueError(
                f"{tool_name}.{key} har ett otillåtet värde."
            )

    return arguments


def normalize_tool_calls(tool_calls):
    normalized = []

    for item in tool_calls or []:
        if isinstance(item, str):
            normalized.append(
                {
                    "name": item,
                    "arguments": {},
                }
            )
            continue

        if not isinstance(item, dict):
            continue

        name = item.get("name") or item.get("tool")
        arguments = item.get(
            "arguments",
            item.get("args", {}),
        )

        if not name or not isinstance(arguments, dict):
            continue

        normalized.append(
            {
                "name": str(name).strip(),
                "arguments": arguments,
            }
        )

    return normalized


def ai_plan_tool_calls(user_input, tools, llm_client):
    """Låt LLM skapa strukturerade verktygsanrop med argument."""
    tool_specs = []

    for name, tool in tools.items():
        tool_specs.append(
            {
                "name": name,
                "description": tool.get("description", ""),
                "parameters": tool.get(
                    "parameters",
                    {
                        "type": "object",
                        "properties": {},
                        "additionalProperties": False,
                    },
                ),
            }
        )

    prompt = f"""
Du är verktygsplanerare för MyAI.

Välj de verktyg som behövs och fyll endast i argument som stöds
av respektive parameters-schema.

Tillgängliga verktyg:
{json.dumps(tool_specs, ensure_ascii=False)}

Användaren frågar:
{user_input}

Svara ENDAST med giltig JSON.

Format:
[
  {{"name": "verktygsnamn", "arguments": {{}}}}
]

Om inget verktyg behövs:
[]
"""

    raw = llm_client.chat(
        [
            {
                "role": "system",
                "content": prompt,
            }
        ],
        timeout=120,
    )

    parsed = json.loads(_strip_json_fence(raw))

    if not isinstance(parsed, list):
        raise ValueError(
            "Verktygsplanen måste vara en JSON-lista."
        )

    calls = normalize_tool_calls(parsed)
    validated = []

    for call in calls:
        name = call["name"]

        if name not in tools:
            continue

        validate_tool_arguments(
            name,
            call["arguments"],
            tools,
        )
        validated.append(call)

    return validated


def select_tool_calls(user_input, tools, llm_client):
    """Välj bakåtkompatibla verktygsanrop med valfria argument."""
    direct_names = detect_tools(user_input)

    if direct_names:
        return [
            {
                "name": name,
                "arguments": {},
            }
            for name in direct_names
            if name in tools
        ]

    try:
        return ai_plan_tool_calls(
            user_input,
            tools,
            llm_client,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        legacy_names = ai_detect_tools(
            user_input,
            tools,
            llm_client,
        )
        return [
            {
                "name": name,
                "arguments": {},
            }
            for name in legacy_names
            if name in tools
        ]


def select_tools(user_input, tools, llm_client):
    """Kompatibilitetsfunktion som returnerar endast verktygsnamn."""
    return [
        call["name"]
        for call in select_tool_calls(
            user_input,
            tools,
            llm_client,
        )
    ]


def run_tools(tool_calls, tools):
    """Kör verktyg med eller utan argument och samla resultaten."""
    results = {}

    for call in normalize_tool_calls(tool_calls):
        tool_name = call["name"]

        if tool_name not in tools:
            continue

        try:
            arguments = validate_tool_arguments(
                tool_name,
                call["arguments"],
                tools,
            )
            tool_function = tools[tool_name]["function"]
            results[tool_name] = tool_function(**arguments)
        except Exception as error:
            results[tool_name] = (
                f"Fel vid körning av {tool_name}: {error}"
            )

    return results
