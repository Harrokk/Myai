import requests

from core.assistant import MyAICore
from core.config import PROJECT_ROOT, load_settings
from core.hardware_monitor import (
    HardwareMonitor,
    format_hardware_changes,
)


SETTINGS = load_settings()
CORE = MyAICore(
    SETTINGS,
    PROJECT_ROOT,
)

# Kompatibilitetsalias medan projektet byggs om stegvis.
TOOLS = CORE.tools
MEMORY = CORE.memory
LLM = CORE.llm
OLLAMA_URL = CORE.ollama_url
MODEL = CORE.model


def _print_hardware_changes(changes):
    text = format_hardware_changes(changes)

    if not text:
        return

    print()
    print("[Hårdvara]")
    print(text)
    print()


def _print_hardware_watch_error(error):
    print()
    print("[Hårdvaruövervakning]")
    print(f"Fel: {error}")
    print()


HARDWARE_MONITOR = HardwareMonitor(
    interval_seconds=SETTINGS.get(
        "hardware_watch",
        {},
    ).get("interval_seconds", 10),
    on_change=_print_hardware_changes,
    on_error=_print_hardware_watch_error,
)


print(f"Verktyg laddade: {len(TOOLS)}")

for tool_name in TOOLS:
    print(f" - {tool_name}")


def main():
    CORE.initialize()

    if SETTINGS.get("hardware_watch", {}).get("enabled", True):
        HARDWARE_MONITOR.start()
    print(f"Verktyg laddade: {len(TOOLS)}")
    print()
    print("==========================================")
    print(f"              {SETTINGS['assistant']['name']}")
    print("==========================================")
    print()
    print(f"Modell:          {MODEL}")
    print(f"Motor:           {SETTINGS['assistant']['engine']}")
    print(f"GPU:             {SETTINGS['assistant']['gpu']}")
    print(f"Långtidsminne:   {SETTINGS['assistant']['memory_label']}")
    print(f"Framtida mål:    {SETTINGS['assistant']['future_target']}")
    print()
    print("Kommandon:")
    print("  /memory        Visa långtidsminne")
    print("  /remember X    Spara X i minnet")
    print("  /clear         Rensa samtalets korttidsminne")
    print("  /watch         Visa hårdvaruövervakningens status")
    print("  /watch on      Starta hårdvaruövervakning")
    print("  /watch off     Stoppa hårdvaruövervakning")
    print("  /exit          Avsluta")
    print()

    while True:
        try:
            user_input = input("Du: ").strip()

        except KeyboardInterrupt:
            HARDWARE_MONITOR.stop()
            print()
            print("Avslutar.")
            break

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            HARDWARE_MONITOR.stop()
            print("Avslutar.")
            break

        if user_input.lower() == "/watch":
            status = (
                "aktiv"
                if HARDWARE_MONITOR.is_running
                else "stoppad"
            )
            print(
                "Hårdvaruövervakning:",
                status,
                f"({HARDWARE_MONITOR.interval_seconds:g} s intervall)",
            )
            print()
            continue

        if user_input.lower() == "/watch on":
            started = HARDWARE_MONITOR.start()

            if started:
                print("Hårdvaruövervakningen startades.")
            elif HARDWARE_MONITOR.is_running:
                print("Hårdvaruövervakningen är redan aktiv.")
            else:
                print("Hårdvaruövervakningen kunde inte startas.")

            print()
            continue

        if user_input.lower() == "/watch off":
            HARDWARE_MONITOR.stop()
            print("Hårdvaruövervakningen stoppades.")
            print()
            continue

        if user_input.lower() == "/clear":
            CORE.clear_conversation()
            print("Korttidsminnet för samtalet är rensat.")
            print()
            continue

        if user_input.lower().startswith("/remember "):
            memory_content = user_input[len("/remember "):].strip()

            if memory_content:
                MEMORY.save("manual", memory_content)
                print("Sparat i långtidsminnet.")
            else:
                print("Inget innehåll att spara.")

            print()
            continue

        if user_input.lower() == "/memory":
            memories = MEMORY.get_all()

            print()
            print("========== LÅNGTIDSMINNE ==========")

            if not memories:
                print("Inget minne sparat.")
            else:
                for memory in memories:
                    memory_id, category, content, created_at = memory
                    print(f"{memory_id}. [{category}] {content}")

            print("===================================")
            print()
            continue

        try:
            print()
            print("AI tänker...")
            print()

            result = CORE.respond(user_input)

            if result["tools"]:
                print("Verktyg:")

                for tool in result["tools"]:
                    print(f" - {tool}")

                print()

            print("AI:")
            print(result["answer"])
            print()

        except requests.exceptions.ConnectionError:
            print()
            print("Kunde inte ansluta till Ollama.")
            print()

        except Exception as error:
            print()
            print("Ett fel uppstod:")
            print(error)
            print()


if __name__ == "__main__":
    main()