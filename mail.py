import requests
import sqlite3
from datetime import datetime

from core.tool_manager import load_tools, run_tools, select_tools


TOOLS = load_tools()

print(f"Verktyg laddade: {len(TOOLS)}")

for tool_name in TOOLS:
    print(f" - {tool_name}")

OLLAMA_URL = "http://localhost:11434/api/chat"
MODEL = "qwen3:8b"
DATABASE = "memory.db"


SYSTEM_PROFILE = """
Du är MyAI, en lokal personlig AI-assistent.

Din språkmodell är Qwen3 8B.
Du körs genom Ollama.
Du kör för närvarande på en Windows-dator.
Datorns GPU är NVIDIA GeForce RTX 3060 med 12 GB VRAM.

Du har ett separat långtidsminne som hanteras av Python och SQLite.

Användaren utvecklar denna AI på Windows och planerar senare
att kunna flytta systemet till en Raspberry Pi 5 B.

Svara på svenska när användaren skriver svenska.
Var saklig och tydlig.
Hitta inte på information om användaren.
Använd information från minnessystemet när den är relevant.
"""

def init_memory():
    conn = sqlite3.connect(DATABASE)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS memories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            category TEXT,
            content TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_memory(category, content):
    conn = sqlite3.connect(DATABASE)

    conn.execute(
        """
        INSERT INTO memories
        (category, content, created_at)
        VALUES (?, ?, ?)
        """,
        (category, content, datetime.now().isoformat())
    )

    conn.commit()
    conn.close()


def get_all_memories():
    conn = sqlite3.connect(DATABASE)

    rows = conn.execute(
        """
        SELECT id, category, content, created_at
        FROM memories
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    return rows


def search_memory(user_message):
    words = user_message.lower().split()

    ignored_words = {
        "jag", "du", "det", "den", "är", "och", "att",
        "har", "kan", "vill", "med", "som", "för",
        "på", "en", "ett", "vad", "hur", "min", "mitt",
        "din", "ditt"
    }

    keywords = [
        word.strip(".,!?")
        for word in words
        if len(word) >= 3 and word not in ignored_words
    ]

    if not keywords:
        return []

    conn = sqlite3.connect(DATABASE)

    results = []

    for keyword in keywords:
        rows = conn.execute(
            """
            SELECT id, category, content, created_at
            FROM memories
            WHERE content LIKE ?
            ORDER BY id DESC
            LIMIT 5
            """,
            (f"%{keyword}%",)
        ).fetchall()

        for row in rows:
            if row not in results:
                results.append(row)

    conn.close()

    return results[:10]


def format_memory(memories):
    if not memories:
        return "Ingen relevant information hittades i långtidsminnet."

    text = ""

    for memory in memories:
        memory_id, category, content, created_at = memory
        text += f"- [{category}] {content}\n"

    return text


def ask_ai(user_message, tool_result=None):
    relevant_memories = search_memory(user_message)

    memory_text = format_memory(relevant_memories)

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
    init_memory()
    print(f"Verktyg laddade: {len(TOOLS)}")
    print()
    print("==========================================")
    print("              MyAI v2")
    print("==========================================")
    print()
    print("Modell:          Qwen3 8B")
    print("Motor:           Ollama")
    print("GPU:             NVIDIA RTX 3060 12 GB")
    print("Långtidsminne:   SQLite")
    print("Framtida mål:    Raspberry Pi 5 B")
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

        if user_input.lower() == "/memory":
            memories = get_all_memories()

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