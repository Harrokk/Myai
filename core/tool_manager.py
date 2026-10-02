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

    mentions_pi = any(
        word in text
        for word in ("raspberry pi", "raspberrypi", "pi 5", "pi5")
    )
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
