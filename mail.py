import requests

from core.assistant import MyAICore
from core.config import PROJECT_ROOT, load_settings


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


print(f"Verktyg laddade: {len(TOOLS)}")

for tool_name in TOOLS:
    print(f" - {tool_name}")


def main():
    CORE.initialize()
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
    print("  /exit          Avsluta")
    print()

    while True:
        try:
            user_input = input("Du: ").strip()

        except KeyboardInterrupt:
            print()
            print("Avslutar.")
            break

        if not user_input:
            continue

        if user_input.lower() == "/exit":
            print("Avslutar.")
            break

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