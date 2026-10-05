from copy import deepcopy

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS


class FakeMemory:
    def __init__(self):
        self.saved = []

    def search(self, user_message):
        return []

    @staticmethod
    def format(memories):
        return "Ingen relevant information hittades."

    def save_if_new(self, category, content):
        self.saved.append((category, content))
        return True


class StreamingLLM:
    provider_name = "test"
    model = "stream-model"
    url = "http://stream-test"

    def chat(self, messages, timeout=300):
        raise AssertionError("chat() ska inte användas när streaming finns.")

    def chat_stream(self, messages, timeout=300):
        yield "CPU "
        yield "är OK."


class NonStreamingLLM:
    provider_name = "test"
    model = "fallback-model"
    url = "http://fallback-test"

    def chat(self, messages, timeout=300):
        return "Fallback-svar"


def _tools():
    return {
        "cpu_status": {
            "function": lambda: "CPU OK",
            "description": "CPU status",
        }
    }


def test_core_streams_chunks_and_saves_complete_turn(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    chunks = []

    core = MyAICore(
        settings,
        tmp_path,
        tools=_tools(),
        memory=FakeMemory(),
        llm=StreamingLLM(),
    )

    result = core.respond_stream(
        "Hur mycket CPU används?",
        on_chunk=chunks.append,
    )

    assert chunks == ["CPU ", "är OK."]
    assert result["answer"] == "CPU är OK."
    assert result["streamed"] is True
    assert result["tools"] == ["cpu_status"]
    assert result["llm_runtime"]["active_backend"] == "primary"
    assert result["llm_runtime"]["provider"] == "test"
    assert result["llm_runtime"]["model"] == "stream-model"
    assert core.conversation_history[-1] == {
        "role": "assistant",
        "content": "CPU är OK.",
    }


def test_core_streaming_falls_back_to_chat(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    chunks = []

    core = MyAICore(
        settings,
        tmp_path,
        tools=_tools(),
        memory=FakeMemory(),
        llm=NonStreamingLLM(),
    )

    result = core.respond_stream(
        "Hur mycket CPU används?",
        on_chunk=chunks.append,
    )

    assert chunks == ["Fallback-svar"]
    assert result["answer"] == "Fallback-svar"
    assert result["streamed"] is False



class RuntimeStatusLLM:
    provider_name = "geniex"
    model = "primary-model"
    url = "http://geniex"

    def chat(self, messages, timeout=300):
        return "Reservsvar"

    def status(self):
        return {
            "enabled": True,
            "active_backend": "fallback",
            "primary_provider": "geniex",
            "primary_model": "primary-model",
            "fallback_provider": "geniex",
            "fallback_model": "fallback-model",
            "last_error": "npu-fel",
        }


def test_core_exposes_degraded_local_llm_runtime_state(tmp_path):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = False
    core = MyAICore(
        settings,
        tmp_path,
        tools={},
        memory=FakeMemory(),
        llm=RuntimeStatusLLM(),
    )

    result = core.respond("Hej")

    runtime = result["llm_runtime"]
    assert runtime["active_backend"] == "fallback"
    assert runtime["fallback_model"] == "fallback-model"
    assert runtime["last_error"] == "npu-fel"
    assert runtime["provider"] == "geniex"
    assert runtime["model"] == "primary-model"
