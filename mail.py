import requests

from core.config import PROJECT_ROOT, load_settings
from core.memory import MemoryStore
from core.tool_manager import load_tools, run_tools, select_tools


TOOLS = load_tools()

print(f"Verktyg laddade: {len(TOOLS)}")

for tool_name in TOOLS:
    print(f" - {tool_name}")

SETTINGS = load_settings()

OLLAMA_URL = SETTINGS["ollama"]["url"]
MODEL = SETTINGS["ollama"]["model"]
DATABASE = PROJECT_ROOT / SETTINGS["memory"]["database"]

MEMORY = MemoryStore(
    DATABASE,
    max_search_results=SETTINGS["memory"]["max_search_results"],
)

SYSTEM_PROFILE = f"""
Du är MyAI, en lokal personlig AI-assistent.

Din språkmodell är {MODEL}.
Du körs genom {SETTINGS["assistant"]["engine"]}.
Du kör för närvarande på en Windows-dator.
Datorns GPU är {SETTINGS["assistant"]["gpu"]}.

Du har ett separat långtidsminne som hanteras av Python och SQLite.

Användaren utvecklar denna AI på Windows och planerar senare
att kunna flytta systemet till en {SETTINGS["assistant"]["future_target"]}.

Svara på svenska när användaren skriver svenska.
Var saklig och tydlig.
Hitta inte på information om användaren.
Använd information från minnessystemet när den är relevant.
"""

def ask_ai(user_message, tool_result=None):
    relevant_memories = MEMORY.search(user_message)

    memory_text = MEMORY.format(relevant_memories)

    system_message = SYSTEM_PROFILE + """

Relevant information från långtidsminnet:

""" + memory_text

    if tool_result is not None:
        system_message += """

Lokala systemverktyg har körts på användarens begäran.

Resultaten från verktygen är:

""" + str(tool_result) + """

Använd resultatet ovan när du svarar på användarens fråga.
Hitta inte på värden som inte finns i resultatet.
Svara kort och tydligt på svenska.
"""

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": system_message
            },
            {
                "role": "user",
                "content": user_message
            }
        ],
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=300
    )

    response.raise_for_status()

    data = response.json()

    return data["message"]["content"]


def main():
    MEMORY.init()
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
            # Välj ett eller flera relevanta verktyg.
            tools_to_run = select_tools(
                user_input,
                TOOLS,
                OLLAMA_URL,
                MODEL,
            )

            # Om ett eller flera verktyg hittades
            if tools_to_run:
                print()
                print("Verktyg:")

                for tool in tools_to_run:
                    print(f" - {tool}")

                print("AI tänker...")
                print()

                tool_results = run_tools(
                    tools_to_run,
                    TOOLS,
                )

                answer = ask_ai(
                    user_input,
                    tool_result=tool_results
                )

                print("AI:")
                print(answer)
                print()

                continue
            print()
            print("AI tänker...")
            print()

            answer = ask_ai(user_input)

            print("AI:")
            print(answer)
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