from core.memory import MemoryStore
from core.memory_policy import assess_memory_candidate
from core.llm_factory import build_llm_client
from core.tool_manager import load_tools, run_tools, select_tools


class MyAICore:
    def __init__(self, settings, project_root, tools=None, memory=None, llm=None):
        self.settings = settings

        self.llm_provider = (
            settings.get("llm", {})
            .get("provider", "ollama")
            .strip()
            .lower()
        )
        self.ollama_url = settings["ollama"]["url"]

        provider_config = (
            settings.get("geniex", {})
            if self.llm_provider == "geniex"
            else settings["ollama"]
        )
        configured_model = provider_config.get(
            "model",
            settings["ollama"]["model"],
        )

        database_path = project_root / settings["memory"]["database"]

        self.memory = memory or MemoryStore(
            database_path,
            max_search_results=settings["memory"]["max_search_results"],
        )

        self.llm = llm or build_llm_client(settings)
        self.llm_provider = getattr(
            self.llm,
            "provider_name",
            self.llm_provider,
        )
        self.model = getattr(
            self.llm,
            "model",
            configured_model,
        )
        self.llm_url = getattr(
            self.llm,
            "url",
            self.ollama_url,
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
        provider_label = {
            "ollama": "Ollama",
            "geniex": "Qualcomm GenieX",
        }.get(
            self.llm_provider,
            self.llm_provider,
        )
        current_platform = assistant.get(
            "current_platform",
            "Windows-dator",
        )

        return f"""
Du är MyAI, en lokal personlig AI-assistent.

Din språkmodell är {self.model}.
Du körs genom {provider_label}.
Du kör för närvarande på {current_platform}.
Beräkningsprofil: {assistant["gpu"]}.

Du har ett separat långtidsminne som hanteras av Python och SQLite.

Utvecklingsmiljön kan använda en annan LLM-provider än målhårdvaran.
Planerad målhårdvara är {assistant["future_target"]}.

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

    def _prior_user_messages(self):
        return [
            item["content"]
            for item in self.conversation_history
            if item.get("role") == "user"
        ]

    def _consider_long_term_memory(self, user_message):
        config = self.settings.get("memory", {})

        if not config.get("auto_assess_enabled", True):
            return {
                "action": "disabled",
                "saved": False,
                "score": 0,
                "category": "other",
                "content": "",
                "sensitive": False,
                "reasons": [
                    "Automatisk minnesbedömning är avstängd."
                ],
            }

        decision = assess_memory_candidate(
            user_message,
            settings=self.settings,
            prior_messages=self._prior_user_messages(),
        )
        decision = dict(decision)
        decision["saved"] = False

        if (
            decision.get("action") == "save"
            and config.get("auto_save_enabled", True)
            and not decision.get("sensitive")
            and decision.get("content")
        ):
            decision["saved"] = bool(
                self.memory.save_if_new(
                    decision["category"],
                    decision["content"],
                )
            )

        return decision

    def _prepare_response(self, user_message):
        tool_names = select_tools(
            user_message,
            self.tools,
            self.llm,
        )

        tool_results = None

        if tool_names:
            tool_results = run_tools(
                tool_names,
                self.tools,
                user_input=user_message,
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

        return tool_names, tool_results, messages

    def _llm_runtime_metadata(self):
        status = getattr(
            self.llm,
            "status",
            None,
        )

        if callable(status):
            runtime = dict(
                status()
            )
        else:
            runtime = {
                "enabled": False,
                "active_backend": "primary",
                "primary_provider": self.llm_provider,
                "primary_model": self.model,
                "fallback_provider": None,
                "fallback_model": None,
                "last_error": None,
            }

        runtime["provider"] = self.llm_provider
        runtime["model"] = self.model
        return runtime

    def _finalize_response(
        self,
        user_message,
        answer,
        tool_names,
        tool_results,
        streamed=False,
    ):
        memory_decision = self._consider_long_term_memory(
            user_message
        )

        self._remember_conversation_turn(
            user_message,
            answer,
        )

        return {
            "answer": answer,
            "tools": tool_names,
            "tool_results": tool_results or {},
            "memory_decision": memory_decision,
            "streamed": bool(streamed),
            "llm_runtime": self._llm_runtime_metadata(),
        }

    def respond(self, user_message):
        (
            tool_names,
            tool_results,
            messages,
        ) = self._prepare_response(user_message)

        answer = self.llm.chat(
            messages,
            timeout=300,
        )

        return self._finalize_response(
            user_message,
            answer,
            tool_names,
            tool_results,
            streamed=False,
        )

    def respond_stream(
        self,
        user_message,
        on_chunk=None,
    ):
        (
            tool_names,
            tool_results,
            messages,
        ) = self._prepare_response(user_message)

        stream = getattr(
            self.llm,
            "chat_stream",
            None,
        )

        if not callable(stream):
            answer = self.llm.chat(
                messages,
                timeout=300,
            )

            if on_chunk is not None and answer:
                on_chunk(answer)

            return self._finalize_response(
                user_message,
                answer,
                tool_names,
                tool_results,
                streamed=False,
            )

        chunks = []

        for chunk in stream(
            messages,
            timeout=300,
        ):
            value = str(chunk or "")

            if not value:
                continue

            chunks.append(value)

            if on_chunk is not None:
                on_chunk(value)

        answer = "".join(chunks)

        return self._finalize_response(
            user_message,
            answer,
            tool_names,
            tool_results,
            streamed=True,
        )

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
