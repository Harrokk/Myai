from pathlib import Path
import sys


PROJECT_ROOT = Path(__file__).resolve().parent.parent

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from core.assistant import MyAICore
from core.config import load_settings
from core.tool_manager import select_tools


EXPECTED_TOOLS = [
    "gpu_status",
    "cpu_status",
    "ram_status",
    "temperature_status",
    "disk_status",
    "usb_status",
    "bluetooth_status",
    "ventuno_rpc_status",
    "ventuno_mcu_status",
]


def print_section(title):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)


def main():
    print_section("MyAI local smoke test")

    settings = load_settings()
    core = MyAICore(
        settings,
        PROJECT_ROOT,
    )
    core.initialize()

    print(f"Modell: {core.model}")
    print(f"LLM-provider: {core.llm_provider}")
    print(f"LLM-endpoint: {core.llm_url}")
    print(f"Verktyg laddade: {len(core.tools)}")

    missing = [
        name
        for name in EXPECTED_TOOLS
        if name not in core.tools
    ]

    if missing:
        print(f"FEL: saknade verktyg: {', '.join(missing)}")
        return 1

    print("Alla förväntade verktyg är laddade.")

    print_section("Multi-tool identifiering")

    selected = select_tools(
        "Hur mycket CPU och RAM använder datorn?",
        core.tools,
        core.llm,
    )

    print("Identifierade verktyg:", ", ".join(selected))

    if selected != ["cpu_status", "ram_status"]:
        print("FEL: multi-tool identifieringen gav oväntat resultat.")
        return 1

    bluetooth_selected = select_tools(
        "Vilka Bluetooth-enheter finns?",
        core.tools,
        core.llm,
    )

    print(
        "Bluetooth-identifiering:",
        ", ".join(bluetooth_selected),
    )

    if bluetooth_selected != ["bluetooth_status"]:
        print("FEL: Bluetooth-frågan valde fel verktyg.")
        return 1

    print_section("Riktiga lokala verktyg")

    for tool_name in EXPECTED_TOOLS:
        print()
        print(f"[{tool_name}]")

        try:
            result = core.tools[tool_name]["function"]()
            print(result)
        except Exception as error:
            print(f"FEL: {error}")
            return 1

    print_section("LLM-provider")

    try:
        llm_answer = core.llm.chat(
            [
                {
                    "role": "user",
                    "content": "Svara endast med ordet OK.",
                }
            ],
            timeout=60,
        )
    except Exception as error:
        print(
            f"FEL: kunde inte få svar från "
            f"{core.llm_provider}: {error}"
        )
        return 1

    print(f"{core.llm_provider} svarade:", llm_answer)

    if not llm_answer.strip():
        print(
            f"FEL: {core.llm_provider} returnerade ett tomt svar."
        )
        return 1

    print_section("Full multi-tool-fråga")

    try:
        response = core.respond(
            "Hur mycket CPU och RAM använder datorn?"
        )
    except Exception as error:
        print(f"FEL: full MyAI-fråga misslyckades: {error}")
        return 1

    print("Verktyg:", ", ".join(response["tools"]))
    print("Svar:")
    print(response["answer"])

    if response["tools"] != ["cpu_status", "ram_status"]:
        print("FEL: full multi-tool-körning använde fel verktyg.")
        return 1

    core.clear_conversation()

    print_section("RESULTAT")
    print("Smoke-testet är godkänt.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
