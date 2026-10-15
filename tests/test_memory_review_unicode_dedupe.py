"""Synthetic pending review deduplication, never reads live VENTUNO memory."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import sqlite3

import pytest

from core.memory import MemoryStore


def store(tmp_path):
    memory = MemoryStore(tmp_path / "synthetic.db")
    memory.init()
    return memory


def test_swedish_unicode_casefold_same_pending_review(tmp_path):
    memory = store(tmp_path)
    initial = memory.enqueue_review(
        "PRÄFERENS", "Ändra på minnesinställningen."
    )
    repeat = memory.enqueue_review(
        "präferens", "ändra på minnesinställningen."
    )
    assert repeat == {"review_id": initial["review_id"], "created": False}
    assert len(memory.list_reviews()) == 1


def test_nfc_combining_diacritics_same_review_preserves_original(tmp_path):
    memory = store(tmp_path)
    original = "Spara A\u0308ndring i projektet."
    first = memory.enqueue_review("Projekt", original)
    second = memory.enqueue_review("projekt", "Spara Ändring i projektet.")
    assert second["review_id"] == first["review_id"]
    assert second["created"] is False
    assert memory.get_review(first["review_id"])["content"] == original


def test_unicode_whitespace_collapse_deduplicates_without_editing_text(tmp_path):
    memory = store(tmp_path)
    first = memory.enqueue_review(
        "project", "Spara  viktig\tinformation\nom projektet."
    )
    second = memory.enqueue_review(
        "PROJECT", "Spara viktig\u00a0information om projektet."
    )
    assert second == {"review_id": first["review_id"], "created": False}
    assert len(memory.list_reviews()) == 1
    assert "\t" in memory.get_review(first["review_id"])["content"]


def test_distinct_meanings_and_categories_remain_separate(tmp_path):
    memory = store(tmp_path)
    memory.enqueue_review("project", "Ändra inställning ett.")
    memory.enqueue_review("project", "Ändra inställning två.")
    memory.enqueue_review("preference", "Ändra inställning ett.")
    assert len(memory.list_reviews()) == 3


def test_equivalent_retry_unions_conflicts_and_cannot_plain_approve(tmp_path):
    memory = store(tmp_path)
    earlier_a = memory.save("preference", "Gammal inställning A")
    earlier_b = memory.save("preference", "Gammal inställning B")
    first = memory.enqueue_review(
        "PRÄFERENS", "Spara  ny inställning",
        conflict_ids=[earlier_a],
    )
    again = memory.enqueue_review(
        "präferens", "spara ny inställning",
        conflict_ids=[earlier_b],
    )
    assert again["review_id"] == first["review_id"]
    assert again["created"] is False
    assert memory.get_review(first["review_id"])["conflict_ids"] == [
        earlier_a, earlier_b
    ]
    with pytest.raises(PermissionError, match="måste ersätta"):
        memory.approve_review(first["review_id"])


def test_concurrent_equivalent_swedish_retries_create_only_one(tmp_path):
    memory = store(tmp_path)
    names = [
        ("PRÄFERENS", "Spara\tÄndrad viktig regel"),
        ("präferens", "spara ändrad viktig regel"),
        ("Präferens", "Spara  ändrad viktig regel"),
        ("präferens", "SPARA ÄNDRAD VIKTIG REGEL"),
        ("PRÄFERENS", "Spara\u00a0ändrad viktig regel"),
        ("präferens", "Spara a\u0308ndrad viktig regel"),
    ]
    barrier = Barrier(len(names))

    def queue(item):
        barrier.wait(timeout=10)
        return memory.enqueue_review(item[0], item[1])

    with ThreadPoolExecutor(max_workers=len(names)) as pool:
        results = list(pool.map(queue, names))

    assert sum(item["created"] for item in results) == 1
    assert len({item["review_id"] for item in results}) == 1
    assert len(memory.list_reviews()) == 1


def test_a_resolved_review_can_be_queued_again(tmp_path):
    memory = store(tmp_path)
    first = memory.enqueue_review("project", "Spara Ändring.")
    memory.reject_review(first["review_id"])
    second = memory.enqueue_review("PROJECT", "Spara ändring.")
    assert second["created"] is True
    assert second["review_id"] != first["review_id"]
    assert memory.get_review(first["review_id"])["status"] == "rejected"
    assert memory.get_review(second["review_id"])["status"] == "pending"
    # list_reviews defaults to pending, so inspect the historical rows
    # directly to ensure the old resolved record was retained.
    with sqlite3.connect(memory.database_path) as conn:
        assert conn.execute(
            "SELECT count(*) FROM memory_reviews"
        ).fetchone()[0] == 2


def test_pending_queue_budget_fails_closed_without_new_record(tmp_path):
    memory = store(tmp_path)
    with sqlite3.connect(memory.database_path) as conn:
        conn.executemany(
            """INSERT INTO memory_reviews
               (category, content, reason, conflicts_json, created_at, status)
               VALUES (?, ?, '', '[]', '2026-10-15', 'pending')""",
            [("project", f"synthetic candidate {number}")
             for number in range(4097)],
        )
    with pytest.raises(ValueError, match="behöver kontrolleras"):
        memory.enqueue_review("project", "En till syntetisk post")
    with sqlite3.connect(memory.database_path) as conn:
        count = conn.execute(
            "SELECT count(*) FROM memory_reviews"
        ).fetchone()[0]
    assert count == 4097
