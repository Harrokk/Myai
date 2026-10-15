"""Offline SQLite memory and dialog fallbacks; never uses real user data."""
from copy import deepcopy
import sqlite3

import pytest

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.memory import MemoryStore


@pytest.mark.parametrize("search,exact,nonmatching", [
    ("100%", "Rabatt 100% nästa gång", "Rabatt 1000 nästa gång"),
    ("a_b", "Ny kod a_b fungerar", "Ny kod aXb fungerar"),
    ("not!ok", "Flaggan not!ok är sparad", "Flaggan not!!ok är annan"),
    ("70%_nu", "Spara 70%_nu i projektet", "Spara 70abcnu i projektet"),
])
def test_memory_like_metacharacters_are_literal(
        tmp_path, search, exact, nonmatching):
    memory = MemoryStore(tmp_path / "synthetic-memory.db")
    memory.init()
    matching_id = memory.save("project", exact)
    memory.save("project", nonmatching)
    found = memory.search(search)
    assert [row[0] for row in found] == [matching_id]
    assert [row[2] for row in found] == [exact]


def test_memory_literal_search_cannot_exfiltrate_unrelated_rows_by_percent(
        tmp_path):
    memory = MemoryStore(tmp_path / "synthetic-memory.db")
    memory.init()
    memory.save("private", "Fiktiva användaruppgifter SECRET_SAMPLE")
    memory.save("project", "Prototyp framsteg 80%")
    result = memory.search("999%")
    assert result == []
    assert "SECRET_SAMPLE" not in str(result)


def test_memory_regular_multitoken_ranking_unchanged(tmp_path):
    store = MemoryStore(tmp_path / "synthetic-memory.db")
    store.init()
    strong = store.save("project", "alpha beta matchas två gånger")
    store.save("project", "alpha är delvis matchning")
    result = store.search("alpha beta")
    assert result[0][0] == strong
    assert len(result) == 2


class FaultMemory:
    def __init__(self, exception_type=sqlite3.OperationalError):
        self.error_type = exception_type
        self.fail = True
        self.store_calls = []
        self.query_calls = []

    def search(self, text):
        self.query_calls.append(text)
        if self.fail:
            raise self.error_type("PRIVATE_DB_PATH_SECRET /tmp/hidden.db")
        return [(1, "project", "Syntetiskt minne", "2026-10-15")]

    def format(self, matches):
        return "\n".join(row[2] for row in matches)

    def save(self, *args):
        self.store_calls.append(("save", args))
        return 1

    def save_if_new(self, *args):
        self.store_calls.append(("save_if_new", args))
        return True


class OfflineLLM:
    def __init__(self):
        self.calls = []
    def chat(self, messages, timeout=300):
        self.calls.append(messages)
        return "Syntetiskt testsvar."
    def chat_stream(self, messages, timeout=300):
        self.calls.append(messages)
        yield "Syntetiskt "
        yield "testsvar."


def create_core(tmp_path, error_type=sqlite3.OperationalError):
    mem = FaultMemory(error_type)
    llm = OfflineLLM()
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = True
    assistant = MyAICore(
        settings, tmp_path, tools={}, memory=mem, llm=llm,
    )
    return assistant, mem, llm


@pytest.mark.parametrize("error_type", [sqlite3.DatabaseError, OSError])
def test_memory_read_failure_preserves_normal_chat_and_defer_save(
        tmp_path, error_type):
    core, mem, llm = create_core(tmp_path, error_type=error_type)
    response = core.respond("Kom ihåg mitt syntetiska projekt.")
    assert response["answer"] == "Syntetiskt testsvar."
    assert response["memory_lookup_status"] == "unavailable"
    assert response["memory_decision"]["saved"] is False
    assert response["memory_decision"]["action"] == (
        "deferred_memory_unavailable"
    )
    assert mem.store_calls == []
    assert len(llm.calls) == 1
    system_message = llm.calls[0][0]["content"]
    assert "tillfälligt otillgängligt" in system_message
    assert "Ingen relevant information hittades" not in system_message
    assert "PRIVATE_DB_PATH_SECRET" not in str(response)
    assert "PRIVATE_DB_PATH_SECRET" not in str(llm.calls)


def test_memory_read_failure_streaming_works_and_skips_auto_save(tmp_path):
    core, mem, llm = create_core(tmp_path)
    emitted = []
    result = core.respond_stream(
        "Kom ihåg ett test.", on_chunk=emitted.append,
    )
    assert result["answer"] == "Syntetiskt testsvar."
    assert result["memory_lookup_status"] == "unavailable"
    assert result["streamed"] is True
    assert "".join(emitted) == result["answer"]
    assert mem.store_calls == []
    assert "PRIVATE_DB_PATH_SECRET" not in str(result)


def test_memory_recovers_on_next_turn_without_permanent_stale_outage(tmp_path):
    core, mem, llm = create_core(tmp_path)
    first = core.respond("Vilket projekt minns du?")
    assert first["memory_lookup_status"] == "unavailable"
    mem.fail = False
    second = core.respond("Vad vet du om mitt projekt?")
    assert second["memory_lookup_status"] == "available"
    assert "Syntetiskt minne" in llm.calls[-1][0]["content"]
    assert "PRIVATE_DB_PATH_SECRET" not in str(second)


def test_unavailable_memory_does_not_clear_existing_conversation(tmp_path):
    core, mem, llm = create_core(tmp_path)
    core.respond("Första syntetiska frågan")
    result = core.respond("Andra syntetiska frågan")
    assert result["memory_lookup_status"] == "unavailable"
    assert [m["role"] for m in core.conversation_history] == [
        "user", "assistant", "user", "assistant"
    ]
    assert len(llm.calls) == 2
