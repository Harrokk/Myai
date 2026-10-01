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
