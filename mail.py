import requests
import sqlite3
from datetime import datetime
import importlib
import pkgutil
import modules


def load_tools():
    tools = {}

    for module_info in pkgutil.walk_packages(
        modules.__path__,
        modules.__name__ + "."
    ):
        module_name = module_info.name

        try:
            module = importlib.import_module(module_name)

            if hasattr(module, "TOOLS"):
                module_tools = module.TOOLS

                if isinstance(module_tools, dict):
                    tools.update(module_tools)

        except Exception as error:
            print(
                f"Varning: kunde inte ladda modulen "
                f"{module_name}: {error}"
            )

    return tools


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

def detect_tools(user_input):
    text = user_input.lower().strip()
    detected_tools = []

    status_words = [
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
        "plats"
    ]

    # Om frågan inte verkar vara en statusfråga
    # låter vi AI:n avgöra själv.
    if not any(word in text for word in status_words):
        return []

    # GPU
    gpu_words = [
        "gpu",
        "grafikkort",
        "grafikkortet",
        "grafik",
        "vram",
        "grafikkortsminne",
        "nvidia",
        "rtx"
    ]

    if any(word in text for word in gpu_words):
        detected_tools.append("gpu_status")

    # CPU
    cpu_words = [
        "cpu",
        "processor",
        "processorn"
    ]

    if any(word in text for word in cpu_words):
        detected_tools.append("cpu_status")

    # RAM
    ram_words = [
        "ram",
        "arbetsminne",
        "ram-minne",
        "ramminne",
        "minnesanvändning",
        "minnes användning"
    ]

    if any(word in text for word in ram_words):
        detected_tools.append("ram_status")

    # Temperatur
    temperature_words = [
        "temperatur",
        "temperaturer",
        "värme",
        "varm",
        "varmt",
        "överhett",
        "överhettad"
    ]

    if any(word in text for word in temperature_words):
        detected_tools.append("temperature_status")

    # Disk / lagring
    disk_words = [
        "disk",
        "hårddisk",
        "ssd",
        "lagring",
        "lagringsutrymme",
        "ledigt utrymme",
        "diskutrymme",
        "disk utrymme"
    ]

    if any(word in text for word in disk_words):
        detected_tools.append("disk_status")

    return detected_tools

def ai_detect_tools(user_input):
    tool_list = "\n".join(
        f"- {name}: {tool['description']}"
        for name, tool in TOOLS.items()
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

    payload = {
        "model": MODEL,
        "messages": [
            {
                "role": "system",
                "content": prompt
            }
        ],
        "stream": False
    }

    response = requests.post(
        OLLAMA_URL,
        json=payload,
        timeout=120
    )

    response.raise_for_status()

    data = response.json()

    result = data["message"]["content"].strip().lower()

    if result == "none":
        return []

    detected_tools = []

    for item in result.split(","):
        tool_name = item.strip()

        if tool_name in TOOLS and tool_name not in detected_tools:
            detected_tools.append(tool_name)

    return detected_tools

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
            # Först försöker vi hitta verktyg direkt.
            tools_to_run = detect_tools(user_input)

            # Om direkt identifiering misslyckas får Qwen välja.
            if not tools_to_run:
                tools_to_run = ai_detect_tools(user_input)

            # Kontrollera att verktygen faktiskt finns.
            tools_to_run = [
                tool for tool in tools_to_run
                if tool in TOOLS
            ]

            # Om ett eller flera verktyg hittades
            if tools_to_run:
                print()
                print("Verktyg:")

                for tool in tools_to_run:
                    print(f" - {tool}")

                tool_results = {}

                print("AI tänker...")
                print()

                for tool in tools_to_run:
                    tool_function = TOOLS[tool]["function"]
                    result = tool_function()
                    tool_results[tool] = result

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