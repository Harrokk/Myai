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


class SequenceLLM:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def chat(self, messages, timeout=300):
        self.calls.append((messages, timeout))
        return self.replies.pop(0)


def test_core_executes_parameterized_tool_call(tmp_path):
    memory = FakeMemory()
    llm = SequenceLLM(
        [
            '[{"name":"lookup_file","arguments":{"filename":"rapport.xlsx"}}]',
            "Filen är behandlad.",
        ]
    )
    tools = {
        "lookup_file": {
            "function": lambda filename: f"läste:{filename}",
            "description": "Läs en fil",
            "parameters": {
                "type": "object",
                "properties": {
                    "filename": {"type": "string"},
                },
                "required": ["filename"],
                "additionalProperties": False,
            },
        }
    }

    core = MyAICore(
        deepcopy(DEFAULT_SETTINGS),
        tmp_path,
        tools=tools,
        memory=memory,
        llm=llm,
    )

    result = core.respond("Läs rapport.xlsx")

    assert result["tools"] == ["lookup_file"]
    assert result["tool_calls"] == [
        {
            "name": "lookup_file",
            "arguments": {
                "filename": "rapport.xlsx",
            },
        }
    ]
    assert result["tool_results"] == {
        "lookup_file": "läste:rapport.xlsx",
    }
    assert result["answer"] == "Filen är behandlad."


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
    assert memory.saved


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
        "Kom ihåg att mitt lösenord är hemligt123."
    )

    assert result["memory_decision"]["sensitive"] is True
    assert result["memory_decision"]["saved"] is False
    assert memory.saved == []


def test_core_reports_review_without_saving(tmp_path):
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
        "Jag föredrar modulär kod framför stora monoliter."
    )

    assert result["memory_decision"]["action"] == "review"
    assert result["memory_decision"]["saved"] is False
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
