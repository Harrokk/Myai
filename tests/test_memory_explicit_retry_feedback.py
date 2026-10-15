"""Synthetic explicit memory retry tests. Never retains or uploads user data."""
from copy import deepcopy
import sqlite3

from core.assistant import MyAICore
from core.config import DEFAULT_SETTINGS
from core.memory import MemoryStore
from core.memory_feedback import explicit_memory_request, memory_write_feedback


class PretendLLM:
    def chat(self, messages, timeout=300):
        return "Jag har sparat det i minnet."
    def chat_stream(self, messages, timeout=300):
        yield "Jag har sparat "
        yield "det i minnet."


class RecoverableMemory(MemoryStore):
    def __init__(self, path):
        super().__init__(path)
        self.outage = False
        self.read_calls = 0
        self.write_calls = 0

    def search(self, text):
        self.read_calls += 1
        if self.outage:
            raise sqlite3.OperationalError("PRIVATE_DB_PATH_ONLY_FOR_TEST")
        return super().search(text)

    def save_if_new(self, category, content):
        self.write_calls += 1
        return super().save_if_new(category, content)


def make_core(tmp_path):
    store = RecoverableMemory(tmp_path / "synthetic-memory.db")
    store.init()
    cfg = deepcopy(DEFAULT_SETTINGS)
    cfg["memory"]["auto_assess_enabled"] = True
    core = MyAICore(cfg, tmp_path, memory=store, tools={}, llm=PretendLLM())
    return core, store


def test_implicit_or_negative_memory_mention_not_a_retry_command():
    for phrase in (
        "Hur fungerar långtidsminnet?",
        "Glöm inte vad jag sa.",
        "Jag vill inte att du sparar det här.",
        "Jag funderar på att skriva kom ihåg i en guide.",
    ):
        assert explicit_memory_request(phrase) is False
    assert explicit_memory_request("Kom ihåg att använda enkla ord") is True
    assert explicit_memory_request("LÄGG PÅ MINNET att vi ses") is True
    assert explicit_memory_request("Spara detta: min regel") is True


def test_memory_outage_does_not_fake_success_or_buffer_old_instruction(tmp_path):
    core, store = make_core(tmp_path)
    store.outage = True
    response = core.respond("Kom ihåg att jag föredrar modulär kod.")
    assert response["memory_lookup_status"] == "unavailable"
    assert response["memory_feedback"]["status"] == "retry_required"
    assert response["answer"].startswith("Minnet sparades inte.")
    assert "PRIVATE_DB_PATH_ONLY_FOR_TEST" not in str(response)
    assert store.write_calls == 0
    assert store.get_all() == []
    assert not hasattr(core, "_pending_memory_retry")
    assert "föredrar modulär" not in response["memory_feedback"]["message"]


def test_retry_requires_full_repeat_then_duplicate_does_not_resave(tmp_path):
    core, store = make_core(tmp_path)
    phrase = "Kom ihåg att jag föredrar modulär kod."
    store.outage = True
    assert core.respond(phrase)["memory_feedback"]["status"] == "retry_required"
    store.outage = False

    # An empty follow-up never infers or auto-replays private old text.
    no_retry = core.respond("Försök igen")
    assert no_retry["memory_feedback"]["status"] == "not_requested"
    assert store.write_calls == 0

    first = core.respond(phrase)
    assert first["memory_feedback"]["status"] == "saved"
    assert first["memory_decision"]["saved"] is True
    assert len(store.get_all()) == 1

    second = core.respond(phrase)
    assert second["memory_feedback"]["status"] == "already_present"
    assert second["memory_decision"]["saved"] is False
    assert len(store.get_all()) == 1
    assert store.write_calls == 1  # Duplicate was rejected by contains().


def test_streaming_outage_does_not_speak_optimistic_saved_claim(tmp_path):
    core, store = make_core(tmp_path)
    store.outage = True
    spoken = []
    response = core.respond_stream(
        "Kom ihåg att jag föredrar modulär kod.",
        on_chunk=spoken.append,
    )
    assert response["memory_feedback"]["status"] == "retry_required"
    assert response["answer"] == "".join(spoken)
    assert "Jag har sparat" not in response["answer"]
    assert len(spoken) == 1
    assert store.write_calls == 0


def test_streaming_success_reports_only_after_save_complete(tmp_path):
    core, store = make_core(tmp_path)
    spoken = []
    response = core.respond_stream(
        "Kom ihåg att jag föredrar modulär kod.",
        on_chunk=spoken.append,
    )
    assert response["memory_feedback"]["status"] == "saved"
    assert len(store.get_all()) == 1
    assert "".join(spoken) == response["answer"]


def test_database_write_error_is_reported_without_raw_data(tmp_path):
    core, store = make_core(tmp_path)
    def fail(*_args):
        raise sqlite3.OperationalError("PRIVATE_FILE_SECRET_TEST")
    store.save_if_new = fail
    response = core.respond("Kom ihåg att jag föredrar modulär kod.")
    assert response["memory_feedback"]["status"] == "retry_required"
    assert "Minnet sparades inte" in response["answer"]
    assert "Jag har sparat" not in response["answer"]
    assert "PRIVATE_FILE_SECRET_TEST" not in str(response)
    assert store.get_all() == []


def test_postwrite_audit_failure_warns_without_replaying(tmp_path):
    core, store = make_core(tmp_path)
    def bad_audit(**_kwargs):
        raise OSError("PRIVATE_AUDIT_PATH_SECRET")
    core.audit_logger.write_result = bad_audit
    response = core.respond("Kom ihåg att jag föredrar modulär kod.")
    assert response["memory_decision"]["saved"] is True
    assert response["memory_feedback"]["status"] == "unverified"
    assert "kan redan vara genomförd" in response["answer"]
    assert "PRIVATE_AUDIT_PATH_SECRET" not in str(response)
    assert len(store.get_all()) == 1
    # An exact explicit repetition still does not duplicate active memory.
    core.respond("Kom ihåg att jag föredrar modulär kod.")
    assert len(store.get_all()) == 1


def test_nonmemory_chat_remains_natural_during_sqlite_outage(tmp_path):
    core, store = make_core(tmp_path)
    store.outage = True
    answer = core.respond("Vad betyder modulär programvara?")
    assert answer["answer"] == "Jag har sparat det i minnet."
    assert answer["memory_feedback"] == {
        "status": "not_requested", "message": ""
    }
    assert answer["memory_lookup_status"] == "unavailable"


def test_review_and_sensitive_memory_feedback_never_claims_persistence():
    review = memory_write_feedback(
        "Spara detta: en projektregel",
        {"action": "review", "review_queued": True, "saved": False},
        "available",
    )
    assert review["status"] == "pending_review"
    refused = memory_write_feedback(
        "Spara detta: min privata information",
        {"action": "ignore", "sensitive": True, "saved": False},
        "available",
    )
    assert refused["status"] == "not_saved_sensitive"
    assert "privata information" not in refused["message"]



def test_database_outage_does_not_invite_repeat_of_sensitive_secret(tmp_path):
    core, store = make_core(tmp_path)
    store.outage = True
    answer = core.respond(
        "Kom ihåg att mitt lösenord är FAKE_ONLY_TEST_PASSWORD."
    )
    assert answer["memory_feedback"]["status"] == "not_saved_sensitive"
    assert "integritetsskäl" in answer["answer"]
    assert "Upprepa" not in answer["answer"]
    assert "FAKE_ONLY_TEST_PASSWORD" not in answer["answer"]
    assert store.write_calls == 0


def test_sensitive_outage_stream_does_not_read_secret_aloud(tmp_path):
    core, store = make_core(tmp_path)
    store.outage = True
    heard = []
    result = core.respond_stream(
        "Spara detta: mitt lösenord är FAKE_ONLY_TEST_PASSWORD.",
        on_chunk=heard.append,
    )
    assert result["memory_feedback"]["status"] == "not_saved_sensitive"
    assert heard == [result["answer"]]
    assert "FAKE_ONLY_TEST_PASSWORD" not in "".join(heard)
    assert "Upprepa" not in "".join(heard)
