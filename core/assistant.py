from core.memory import MemoryStore
from core.ollama_client import OllamaClient
from core.tool_manager import load_tools, run_tools, select_tool_calls


class MyAICore:
    def __init__(self, settings, project_root, tools=None, memory=None, llm=None):
        self.settings = settings

        self.ollama_url = settings["ollama"]["url"]
        self.model = settings["ollama"]["model"]

        database_path = project_root / settings["memory"]["database"]

        self.memory = memory or MemoryStore(
            database_path,
            max_search_results=settings["memory"]["max_search_results"],
        )

        self.llm = llm or OllamaClient(
            self.ollama_url,
            self.model,
        )

        self.tools = tools if tools is not None else load_tools()
        self.max_conversation_turns = settings.get(
            "conversation",
            {},
        ).get("max_turns", 6)
        self.conversation_history = []
        self.system_profile = self._build_system_profile()

    def _build_system_profile(self):
        assistant = self.settings["assistant"]

        return f"""
Du är MyAI, en lokal personlig AI-assistent.

Din språkmodell är {self.model}.
Du körs genom {assistant["engine"]}.
Du kör för närvarande på en Windows-dator.
Datorns GPU är {assistant["gpu"]}.

Du har ett separat långtidsminne som hanteras av Python och SQLite.

Användaren utvecklar denna AI på Windows och planerar senare
att kunna flytta systemet till en {assistant["future_target"]}.

Svara på svenska när användaren skriver svenska.
Var saklig och tydlig.
Hitta inte på information om användaren.
Använd information från minnessystemet när den är relevant.
"""

    def initialize(self):
        self.memory.init()

    def build_system_message(self, user_message, tool_results=None):
        relevant_memories = self.memory.search(user_message)
        memory_text = self.memory.format(relevant_memories)

        system_message = (
            self.system_profile
            + """

Relevant information från långtidsminnet:

"""
            + memory_text
        )

        if tool_results is not None:
            system_message += (
                """

Lokala systemverktyg har körts på användarens begäran.

Resultaten från verktygen är:

"""
                + str(tool_results)
                + """

Använd resultatet ovan när du svarar på användarens fråga.
Hitta inte på värden som inte finns i resultatet.
Svara kort och tydligt på svenska.
"""
            )

        return system_message

    def respond(self, user_message):
        tool_calls = select_tool_calls(
            user_message,
            self.tools,
            self.llm,
        )
        tool_names = [
            call["name"]
            for call in tool_calls
        ]

        tool_results = None

        if tool_calls:
            tool_results = run_tools(
                tool_calls,
                self.tools,
            )

        system_message = self.build_system_message(
            user_message,
            tool_results=tool_results,
        )

        messages = [
            {
                "role": "system",
                "content": system_message,
            }
        ]

        messages.extend(self.conversation_history)

        messages.append(
            {
                "role": "user",
                "content": user_message,
            }
        )

        answer = self.llm.chat(
            messages,
            timeout=300,
        )

        self._remember_conversation_turn(
            user_message,
            answer,
        )

        return {
            "answer": answer,
            "tools": tool_names,
            "tool_calls": tool_calls,
            "tool_results": tool_results or {},
        }

    def _remember_conversation_turn(self, user_message, answer):
        if self.max_conversation_turns <= 0:
            self.conversation_history = []
            return

        self.conversation_history.extend(
            [
                {
                    "role": "user",
                    "content": user_message,
                },
                {
                    "role": "assistant",
                    "content": answer,
                },
            ]
        )

        max_messages = self.max_conversation_turns * 2

        if len(self.conversation_history) > max_messages:
            self.conversation_history = self.conversation_history[-max_messages:]

    def clear_conversation(self):
        self.conversation_history = []
