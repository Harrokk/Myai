"""Only synthetic SQLite and fake LLM; never genuine user memory."""
from copy import deepcopy
import sqlite3

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.memory import MemoryStore


class FakeLLM:
    def __init__(self, *, supports_stream=True):
        self.calls = []
        self.supports_stream = supports_stream

    def chat(self, messages, timeout=300):
        self.calls.append(("chat", messages))
        # Deliberately misleading model claim. MyAI must not propagate
        # this as a persistence result if the database save failed.
        return "Det är redan sparat, enligt språkmodellen."

    def chat_stream(self, messages, timeout=300):
        self.calls.append(("stream", messages))
        yield "Det är redan "
        yield "sparat, enligt språkmodellen."


def make_core(tmp_path, *, memory=None):
    settings = deepcopy(DEFAULT_SETTINGS)
    settings["memory"]["auto_assess_enabled"] = True
    settings["memory"]["auto_save_enabled"] = True
    store = memory or MemoryStore(tmp_path / "synthetic-memory.db")
    if isinstance(store, MemoryStore):
        store.init()
    llm = FakeLLM()
    core = MyAICore(
        settings, tmp_path, memory=store, llm=llm, tools={},
    )
    return core, store, llm


def test_successful_explicit_memory_response_comes_from_actual_sqlite(tmp_path):
    core, store, llm = make_core(tmp_path)
    result = core.respond("Kom ihåg att jag föredrar syntetisk modulär kod.")
    assert result["memory_decision"]["saved"] is True
    assert result["answer"] == "Uppgiften har sparats i långtidsminnet."
    assert result["memory_acknowledgement"] == result["answer"]
    assert len(store.get_all()) == 1
    assert core.conversation_history[-1]["content"] == result["answer"]
    assert "enligt språkmodellen" not in result["answer"]


def test_duplicate_explicit_memory_never_claims_new_save(tmp_path):
    core, store, _ = make_core(tmp_path)
    prompt = "Kom ihåg att jag föredrar syntetisk modulär kod."
    first = core.respond(prompt)
    second = core.respond(prompt)
    assert first["memory_decision"]["saved"] is True
    assert second["memory_decision"]["saved"] is False
    assert second["memory_decision"]["lifecycle_action"] == "duplicate"
    assert second["answer"] == "Uppgiften finns redan i långtidsminnet."
    assert len(store.get_all()) == 1


def test_failed_explicit_memory_store_cannot_be_falsely_confirmed(
        tmp_path, monkeypatch):
    core, store, llm = make_core(tmp_path)
    def refuse_save(*args, **kwargs):
        raise sqlite3.OperationalError(
            "PRIVATE_DB_PATH_AND_SECRET /home/arduino/memory.db"
        )
    monkeypatch.setattr(store, "save_if_new", refuse_save)
    result = core.respond("Kom ihåg att jag föredrar syntetisk modulär kod.")
    assert result["memory_decision"]["saved"] is False
    assert result["memory_decision"]["lifecycle_action"] == "failed"
    assert result["answer"] == (
        "Uppgiften kunde inte sparas i långtidsminnet. Försök igen senare."
    )
    assert result["memory_acknowledgement"] == result["answer"]
    assert "PRIVATE_DB_PATH_AND_SECRET" not in str(result)
    assert store.get_all() == []
    assert core.conversation_history[-1]["content"] == result["answer"]


def test_memory_read_outage_has_truthful_direct_confirmation(tmp_path, monkeypatch):
    core, store, _ = make_core(tmp_path)
    def broken_search(_message):
        raise sqlite3.DatabaseError("PRIVATE_READ_SECRET")
    monkeypatch.setattr(store, "search", broken_search)
    result = core.respond("Kom ihåg att jag föredrar syntetiska exempel.")
    assert result["memory_lookup_status"] == "unavailable"
    assert result["memory_decision"]["saved"] is False
    assert result["answer"].startswith("Uppgiften sparades inte.")
    assert "Försök igen" in result["answer"]
    assert "PRIVATE_READ_SECRET" not in str(result)
    assert store.get_all() == []


def test_streamed_memory_command_does_not_emit_model_save_claim_on_failure(
        tmp_path, monkeypatch):
    core, store, _ = make_core(tmp_path)
    def fail_save(*_args, **_kwargs):
        raise sqlite3.OperationalError("PRIVATE_EXPLICIT_SAVE_FAILURE")
    monkeypatch.setattr(store, "save_if_new", fail_save)
    chunks = []
    result = core.respond_stream(
        "Kom ihåg att jag föredrar syntetiska exempel.",
        on_chunk=chunks.append,
    )
    assert result["memory_decision"]["saved"] is False
    assert chunks == [result["answer"]]
    assert "enligt språkmodellen" not in "".join(chunks)
    assert "PRIVATE_EXPLICIT_SAVE_FAILURE" not in str(result)
    assert result["streamed"] is True


def test_streamed_memory_command_emits_actual_success_only_after_save(tmp_path):
    core, store, _ = make_core(tmp_path)
    chunks = []
    result = core.respond_stream(
        "Kom ihåg att jag föredrar syntetiska exempel.",
        on_chunk=chunks.append,
    )
    assert result["memory_decision"]["saved"] is True
    assert chunks == ["Uppgiften har sparats i långtidsminnet."]
    assert chunks == [result["answer"]]
    assert len(store.get_all()) == 1


def test_sensitive_explicit_memory_does_not_echo_secret_or_claim_save(tmp_path):
    core, store, _ = make_core(tmp_path)
    result = core.respond("Kom ihåg att mitt lösenord är SECRET_PASSWORD_FOR_TEST.")
    assert result["memory_decision"]["sensitive"] is True
    assert result["memory_decision"]["saved"] is False
    assert result["answer"] == (
        "Uppgiften sparades inte eftersom den kan innehålla "
        "känslig information."
    )
    assert "SECRET_PASSWORD_FOR_TEST" not in result["answer"]
    assert store.get_all() == []


def test_disabled_auto_memory_does_not_claim_save(tmp_path):
    core, store, _ = make_core(tmp_path)
    core.settings["memory"]["auto_assess_enabled"] = False
    result = core.respond("Kom ihåg att jag föredrar syntetiska exempel.")
    assert result["memory_decision"]["saved"] is False
    assert result["answer"].startswith("Uppgiften sparades inte.")
    assert store.get_all() == []


def test_normal_question_keeps_llm_answer_and_incremental_streaming(tmp_path):
    core, store, _ = make_core(tmp_path)
    chunks = []
    result = core.respond_stream(
        "Vad är modulär kod?", on_chunk=chunks.append,
    )
    assert result["memory_acknowledgement"] is None
    assert result["answer"] == "Det är redan sparat, enligt språkmodellen."
    assert chunks == ["Det är redan ", "sparat, enligt språkmodellen."]


def test_mentioning_memory_phrase_inside_question_is_not_an_explicit_save(tmp_path):
    core, store, _ = make_core(tmp_path)
    result = core.respond("Vad betyder uttrycket kom ihåg i ett program?")
    assert result["memory_acknowledgement"] is None
    assert result["answer"] == "Det är redan sparat, enligt språkmodellen."
    assert store.get_all() == []
