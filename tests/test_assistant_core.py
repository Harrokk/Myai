from copy import deepcopy

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS


class FakeMemory:
    def __init__(self):
        self.initialized = False
        self.saved = []

    def init(self):
        self.initialized = True

    def save(self, category, content):
        self.saved.append((category, content))

    def save_if_new(self, category, content):
        item = (category, content)

        if item in self.saved:
            return False

        self.saved.append(item)
        return True

    def get_all(self):
        return []

    def search(self, user_message):
        return []

    @staticmethod
    def format(memories):
        return "Ingen relevant information hittades i långtidsminnet."


class FakeLLM:
    def __init__(self):
        self.calls = []

    def chat(self, messages, timeout=300):
        self.calls.append((messages, timeout))
        return "Samlat testsvar"


def test_core_initializes_memory(tmp_path):
    memory = FakeMemory()
    llm = FakeLLM()

    core = MyAICore(
        deepcopy(DEFAULT_SETTINGS),
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    core.initialize()

    assert memory.initialized is True


def test_core_runs_multiple_tools_and_builds_one_answer(tmp_path):
    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "CPU status",
        },
        "ram_status": {
            "function": lambda: "RAM OK",
            "description": "RAM status",
        },
    }

    core = MyAICore(
        deepcopy(DEFAULT_SETTINGS),
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Hur mycket CPU och RAM använder datorn?"
    )

    assert result["tools"] == ["cpu_status", "ram_status"]
    assert result["tool_results"] == {
        "cpu_status": "CPU OK",
        "ram_status": "RAM OK",
    }
    assert result["answer"] == "Samlat testsvar"

    assert len(llm.calls) == 1
    system_message = llm.calls[0][0][0]["content"]

    assert "CPU OK" in system_message
    assert "RAM OK" in system_message


def test_core_keeps_short_term_conversation_history(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["conversation"]["max_turns"] = 2

    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "CPU status",
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    core.respond("Hur mycket CPU används?")
    core.respond("Hur mycket CPU används nu?")

    second_messages = llm.calls[1][0]

    assert second_messages[1] == {
        "role": "user",
        "content": "Hur mycket CPU används?",
    }
    assert second_messages[2] == {
        "role": "assistant",
        "content": "Samlat testsvar",
    }


def test_core_can_clear_short_term_history(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "CPU status",
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    core.respond("Hur mycket CPU används?")
    assert core.conversation_history

    core.clear_conversation()

    assert core.conversation_history == []


def test_short_term_history_is_bounded(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["conversation"]["max_turns"] = 1

    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "CPU status",
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    core.respond("Hur mycket CPU används?")
    core.respond("Hur mycket CPU används nu?")

    assert len(core.conversation_history) == 2
    assert core.conversation_history[0]["content"] == (
        "Hur mycket CPU används nu?"
    )



def test_core_passes_user_message_to_query_aware_tool(tmp_path):
    memory = FakeMemory()
    llm = FakeLLM()
    seen = {}

    tools = {
        "internet_search": {
            "function": lambda query: seen.setdefault("query", query) or "SEARCH OK",
            "description": "Internet search",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        deepcopy(DEFAULT_SETTINGS),
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    result = core.respond("Sök på internet efter Raspberry Pi 5")

    assert result["tools"] == ["internet_search"]
    assert seen["query"] == "Sök på internet efter Raspberry Pi 5"


def test_core_auto_saves_explicit_memory_request(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Kom ihåg att jag föredrar modulär kod."
    )

    assert result["memory_decision"]["action"] == "save"
    assert result["memory_decision"]["saved"] is True
    assert memory.saved == [
        ("preference", "jag föredrar modulär kod.")
    ]


def test_core_does_not_auto_save_sensitive_memory(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Kom ihåg att mitt lösenord är hunter2."
    )

    assert result["memory_decision"]["action"] == "ignore"
    assert result["memory_decision"]["sensitive"] is True
    assert memory.saved == []


def test_core_can_disable_auto_memory_assessment(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    memory = FakeMemory()
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Kom ihåg att jag föredrar modulär kod."
    )

    assert result["memory_decision"]["action"] == "disabled"
    assert memory.saved == []


def test_core_explicit_rule_update_supersedes_old_memory(tmp_path):
    from core.memory import MemoryStore

    settings = deepcopy(DEFAULT_SETTINGS)
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    old_id = memory.save(
        "rule",
        "Prisjämförelser ska använda tre kandidater.",
    )
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Från och med nu ska prisjämförelser använda fem kandidater."
    )

    decision = result[
        "memory_decision"
    ]
    assert decision[
        "action"
    ] == "save"
    assert decision[
        "saved"
    ] is True
    assert decision[
        "lifecycle_action"
    ] == "superseded"
    assert decision[
        "superseded_memory_id"
    ] == old_id

    active = memory.get_all()
    assert len(
        active
    ) == 1
    assert "fem kandidater" in active[
        0
    ][
        2
    ]

    history = memory.get_history()
    previous = next(
        item
        for item in history
        if item[
            "id"
        ]
        == old_id
    )
    assert previous[
        "status"
    ] == "superseded"


def test_core_queues_policy_review_candidate(tmp_path):
    from core.memory import MemoryStore

    settings = deepcopy(DEFAULT_SETTINGS)
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Jag föredrar modulär kod."
    )

    decision = result[
        "memory_decision"
    ]
    assert decision[
        "action"
    ] == "review"
    assert decision[
        "review_queued"
    ] is True
    assert decision[
        "review_created"
    ] is True

    reviews = memory.list_reviews()
    assert len(
        reviews
    ) == 1
    assert reviews[
        0
    ][
        "content"
    ] == "Jag föredrar modulär kod."


def test_core_queues_ambiguous_lifecycle_conflict(tmp_path):
    from core.memory import MemoryStore

    settings = deepcopy(DEFAULT_SETTINGS)
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    first = memory.save(
        "rule",
        "Prisjämförelser ska använda tre kandidater.",
    )
    second = memory.save(
        "rule",
        "Prisjämförelser använder fyra kandidater.",
    )
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Från och med nu ska prisjämförelser använda fem kandidater."
    )

    decision = result[
        "memory_decision"
    ]
    assert decision[
        "action"
    ] == "review"
    assert decision[
        "review_queued"
    ] is True

    review = memory.get_review(
        decision[
            "review_id"
        ]
    )
    assert set(
        review[
            "conflict_ids"
        ]
    ) == {
        first,
        second,
    }
    assert len(
        memory.get_all()
    ) == 2


def test_core_memory_audit_failure_blocks_auto_store_without_crashing(
    tmp_path,
    monkeypatch,
):
    from core.audit_log import AuditLogger
    from core.memory import MemoryStore

    settings = deepcopy(DEFAULT_SETTINGS)
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    llm = FakeLLM()
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=memory,
        llm=llm,
    )

    def fail_attempt(
        self,
        **kwargs,
    ):
        raise RuntimeError(
            "synthetic audit failure"
        )

    monkeypatch.setattr(
        AuditLogger,
        "write_attempt",
        fail_attempt,
    )

    result = core.respond(
        "Kom ihåg att jag föredrar modulär kod."
    )

    decision = result[
        "memory_decision"
    ]
    assert decision[
        "saved"
    ] is False
    assert decision[
        "lifecycle_action"
    ] == "audit_blocked"
    assert memory.get_all() == []


def test_core_executes_safe_multidomain_orchestration_with_clause_query(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    seen = {}

    tools = {
        "weather_forecast": {
            "function": lambda query: (
                seen.setdefault(
                    "weather_query",
                    query,
                )
                or "WEATHER"
            ),
            "description": "weather",
            "pass_user_input": True,
        },
        "ram_status": {
            "function": lambda: "RAM OK",
            "description": "ram",
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )
    result = core.respond(
        (
            "Vad blir det för väder i Stockholm idag "
            "och hur mycket RAM används?"
        )
    )

    assert result[
        "tools"
    ] == [
        "weather_forecast",
        "ram_status",
    ]
    assert result[
        "orchestration_plan"
    ][
        "orchestrated"
    ] is True
    assert seen[
        "weather_query"
    ] == (
        "Vad blir det för väder i Stockholm idag"
    )
    assert (
        "input"
        not in result[
            "orchestration_plan"
        ][
            "steps"
        ][
            0
        ]
    )


def test_core_executes_camera_before_vision_in_orchestrated_plan(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    order = []

    tools = {
        "camera_capture": {
            "function": lambda: (
                order.append(
                    "capture"
                )
                or "CAPTURED"
            ),
            "description": "capture",
        },
        "vision_analyze": {
            "function": lambda: (
                order.append(
                    "vision"
                )
                or "VISION"
            ),
            "description": "vision",
        },
        "cpu_status": {
            "function": lambda: (
                order.append(
                    "cpu"
                )
                or "CPU"
            ),
            "description": "cpu",
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )
    result = core.respond(
        (
            "Ta en bild och analysera bilden "
            "och visa CPU status"
        )
    )

    assert result[
        "tools"
    ] == [
        "camera_capture",
        "vision_analyze",
        "cpu_status",
    ]
    assert order == [
        "capture",
        "vision",
        "cpu",
    ]
    assert result[
        "orchestration_plan"
    ][
        "steps"
    ][
        0
    ][
        "effect"
    ] == "local_capture"


def test_core_defers_visual_research_and_returns_confirmation_command(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    calls = []

    tools = {
        "camera_capture": {
            "function": lambda: (
                calls.append(
                    "capture"
                )
                or "Kamerabild sparad lokalt."
            ),
            "description": "capture",
        },
        "vision_analyze": {
            "function": lambda: (
                calls.append(
                    "vision"
                )
                or (
                    "Bildanalys av capture.jpg:\n"
                    "En röd industrikontakt med fyra stift."
                )
            ),
            "description": "vision",
        },
        "research_top_three": {
            "function": lambda query: (
                calls.append(
                    (
                        "research",
                        query,
                    )
                )
                or "RESEARCH"
            ),
            "description": "research",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )
    result = core.respond(
        (
            "Ta en bild och analysera bilden "
            "och researcha det du ser"
        )
    )

    assert calls == [
        "capture",
        "vision",
    ]
    pending = result[
        "pending_intermediate_results"
    ]
    assert len(
        pending
    ) == 1
    assert pending[
        0
    ][
        "confirmation_command"
    ] == "FORTSÄTT MED RESEARCH IR1"
    assert pending[
        0
    ][
        "next_tool"
    ] == "research_top_three"
    assert "industrikontakt" in pending[
        0
    ][
        "query_preview"
    ]
    system_message = llm.calls[
        0
    ][
        0
    ][
        0
    ][
        "content"
    ]
    assert "HAR INTE körts" in system_message
    assert "FORTSÄTT MED RESEARCH IR1" in system_message


def test_core_runs_confirmed_research_once_with_bounded_vision_query(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()
    seen = []

    tools = {
        "vision_analyze": {
            "function": lambda: (
                "Bildanalys av capture.jpg:\n"
                "En röd industrikontakt med fyra stift."
            ),
            "description": "vision",
        },
        "research_top_three": {
            "function": lambda query: (
                seen.append(
                    query
                )
                or "RESEARCH OK"
            ),
            "description": "research",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    first = core.respond(
        "Analysera bilden och researcha det du ser"
    )
    command = first[
        "pending_intermediate_results"
    ][
        0
    ][
        "confirmation_command"
    ]

    second = core.respond(
        command
    )

    assert second[
        "tools"
    ] == [
        "research_top_three"
    ]
    assert second[
        "orchestration_plan"
    ][
        "source"
    ] == "confirmed_intermediate"
    assert seen == [
        "En röd industrikontakt med fyra stift."
    ]
    assert second[
        "pending_intermediate_results"
    ] == []

    third = core.respond(
        command
    )
    assert third[
        "tools"
    ] == []
    assert "okänd eller har gått ut" in third[
        "tool_results"
    ][
        "intermediate_protocol"
    ]
    assert len(
        seen
    ) == 1


def test_failed_vision_result_does_not_create_followup(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "vision_analyze": {
            "function": lambda: (
                "Visionanalysen misslyckades: modell saknas"
            ),
            "description": "vision",
        },
        "research_top_three": {
            "function": lambda query: "RESEARCH",
            "description": "research",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    result = core.respond(
        "Analysera bilden och researcha det du ser"
    )

    assert result[
        "pending_intermediate_results"
    ] == []
    assert "research_top_three" not in result[
        "tools"
    ]


def test_lowercase_confirmation_does_not_consume_pending_result(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "vision_analyze": {
            "function": lambda: (
                "Bildanalys av capture.jpg:\nkontakt"
            ),
            "description": "vision",
        },
        "research_top_three": {
            "function": lambda query: "RESEARCH",
            "description": "research",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    first = core.respond(
        "Analysera bilden och researcha det du ser"
    )
    identifier = first[
        "pending_intermediate_results"
    ][
        0
    ][
        "id"
    ]

    core.respond(
        f"fortsätt med research {identifier}"
    )

    assert core.intermediate_results.get(
        identifier
    ) is not None


def test_clear_conversation_clears_pending_intermediate_results(
    tmp_path,
):
    settings = deepcopy(DEFAULT_SETTINGS)
    memory = FakeMemory()
    llm = FakeLLM()

    tools = {
        "vision_analyze": {
            "function": lambda: (
                "Bildanalys av capture.jpg:\nkontakt"
            ),
            "description": "vision",
        },
        "research_top_three": {
            "function": lambda query: "RESEARCH",
            "description": "research",
            "pass_user_input": True,
        },
    }

    core = MyAICore(
        settings,
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )
    first = core.respond(
        "Analysera bilden och researcha det du ser"
    )
    identifier = first[
        "pending_intermediate_results"
    ][
        0
    ][
        "id"
    ]

    core.clear_conversation()

    assert core.intermediate_results.get(
        identifier
    ) is None
