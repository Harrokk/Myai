import sqlite3
from datetime import datetime

from core.memory import MemoryStore
from core.memory_lifecycle import (
    apply_memory_lifecycle,
    find_memory_conflicts,
    has_replacement_signal,
)


def decision(
    category,
    content,
):
    return {
        "action": "save",
        "category": category,
        "content": content,
        "sensitive": False,
    }


def lifecycle_settings():
    return {
        "memory": {
            "lifecycle_enabled": True,
            "auto_supersede_explicit_updates": True,
            "conflict_similarity_threshold": 0.65,
            "supersede_similarity_threshold": 0.85,
            "max_conflict_scan": 200,
            "stale_after_days": 0,
        }
    }


def test_init_migrates_legacy_memory_table_without_data_loss(
    tmp_path,
):
    path = tmp_path / "memory.db"

    with sqlite3.connect(
        path
    ) as conn:
        conn.execute(
            """
            CREATE TABLE memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                category TEXT,
                content TEXT,
                created_at TEXT
            )
            """
        )
        conn.execute(
            """
            INSERT INTO memories
            (category, content, created_at)
            VALUES (?, ?, ?)
            """,
            (
                "manual",
                "Legacy memory",
                "2026-01-01T00:00:00",
            ),
        )

    memory = MemoryStore(
        path
    )
    memory.init()

    with sqlite3.connect(
        path
    ) as conn:
        columns = {
            row[1]
            for row in conn.execute(
                "PRAGMA table_info(memories)"
            ).fetchall()
        }

    assert {
        "status",
        "updated_at",
        "superseded_by",
        "superseded_at",
    }.issubset(
        columns
    )
    assert memory.get_all()[
        0
    ][
        2
    ] == "Legacy memory"


def test_supersede_is_non_destructive_and_searches_only_active_memory(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    old_id = memory.save(
        "rule",
        "Prisjämförelser använder tre kandidater.",
    )

    new_id = memory.supersede(
        old_id,
        "rule",
        "Prisjämförelser använder fem kandidater.",
    )

    active = memory.get_all()
    history = memory.get_history()

    assert len(
        active
    ) == 1
    assert active[
        0
    ][
        0
    ] == new_id
    assert "fem kandidater" in active[
        0
    ][
        2
    ]

    old = next(
        item
        for item in history
        if item[
            "id"
        ]
        == old_id
    )
    new = next(
        item
        for item in history
        if item[
            "id"
        ]
        == new_id
    )

    assert old[
        "status"
    ] == "superseded"
    assert old[
        "superseded_by"
    ] == new_id
    assert old[
        "superseded_at"
    ]
    assert new[
        "status"
    ] == "active"

    results = memory.search(
        "tre kandidater"
    )
    assert all(
        row[
            0
        ]
        != old_id
        for row in results
    )


def test_explicit_high_confidence_update_supersedes_single_memory(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    old_id = memory.save(
        "rule",
        "Prisjämförelser ska använda tre kandidater.",
    )

    outcome = apply_memory_lifecycle(
        memory,
        decision(
            "rule",
            (
                "Från och med nu ska prisjämförelser "
                "använda fem kandidater."
            ),
        ),
        original_text=(
            "Från och med nu ska prisjämförelser "
            "använda fem kandidater."
        ),
        settings=lifecycle_settings(),
    )

    assert outcome[
        "saved"
    ] is True
    assert outcome[
        "lifecycle_action"
    ] == "superseded"
    assert outcome[
        "superseded_memory_id"
    ] == old_id
    assert outcome[
        "new_memory_id"
    ] != old_id
    assert len(
        memory.get_all()
    ) == 1


def test_ambiguous_explicit_update_requires_review_and_changes_nothing(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    memory.save(
        "rule",
        "Prisjämförelser ska använda tre kandidater.",
    )
    memory.save(
        "rule",
        "Prisjämförelser använder fyra kandidater.",
    )

    outcome = apply_memory_lifecycle(
        memory,
        decision(
            "rule",
            (
                "Från och med nu ska prisjämförelser "
                "använda fem kandidater."
            ),
        ),
        original_text=(
            "Från och med nu ska prisjämförelser "
            "använda fem kandidater."
        ),
        settings=lifecycle_settings(),
    )

    assert outcome[
        "saved"
    ] is False
    assert outcome[
        "requires_review"
    ] is True
    assert outcome[
        "lifecycle_action"
    ] == "ambiguous_replacement"
    assert len(
        memory.get_all()
    ) == 2


def test_possible_conflict_without_update_signal_requires_review(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    memory.save(
        "preference",
        "Jag föredrar korta tekniska svar.",
    )

    outcome = apply_memory_lifecycle(
        memory,
        decision(
            "preference",
            "Jag föredrar utförliga tekniska svar.",
        ),
        original_text=(
            "Jag föredrar utförliga tekniska svar."
        ),
        settings=lifecycle_settings(),
    )

    assert outcome[
        "saved"
    ] is False
    assert outcome[
        "requires_review"
    ] is True
    assert outcome[
        "lifecycle_action"
    ] == "possible_conflict"


def test_unrelated_memory_saves_normally(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    memory.save(
        "preference",
        "Jag föredrar modulär kod.",
    )

    outcome = apply_memory_lifecycle(
        memory,
        decision(
            "preference",
            "Jag föredrar citron i fiskrätter.",
        ),
        original_text=(
            "Jag föredrar citron i fiskrätter."
        ),
        settings=lifecycle_settings(),
    )

    assert outcome[
        "saved"
    ] is True
    assert outcome[
        "lifecycle_action"
    ] == "saved"
    assert len(
        memory.get_all()
    ) == 2


def test_exact_duplicate_is_not_saved_or_sent_to_review(
    tmp_path,
):
    memory = MemoryStore(
        tmp_path
        / "memory.db"
    )
    memory.init()
    memory.save(
        "preference",
        "Jag föredrar modulär kod.",
    )

    outcome = apply_memory_lifecycle(
        memory,
        decision(
            "preference",
            "Jag föredrar modulär kod.",
        ),
        original_text=(
            "Jag föredrar modulär kod."
        ),
        settings=lifecycle_settings(),
    )

    assert outcome[
        "saved"
    ] is False
    assert outcome[
        "requires_review"
    ] is False
    assert outcome[
        "lifecycle_action"
    ] == "duplicate"


def test_stale_listing_is_read_only_and_disabled_by_zero_days(
    tmp_path,
):
    path = (
        tmp_path
        / "memory.db"
    )
    memory = MemoryStore(
        path
    )
    memory.init()
    memory_id = memory.save(
        "project",
        "Projektet ska använda modulär arkitektur.",
    )

    with sqlite3.connect(
        path
    ) as conn:
        conn.execute(
            """
            UPDATE memories
            SET created_at = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (
                "2020-01-01T00:00:00",
                "2020-01-01T00:00:00",
                memory_id,
            ),
        )

    assert memory.list_stale(
        max_age_days=0,
        now=datetime(
            2026,
            1,
            1,
        ),
    ) == []

    stale = memory.list_stale(
        max_age_days=30,
        now=datetime(
            2026,
            1,
            1,
        ),
    )

    assert len(
        stale
    ) == 1
    assert stale[
        0
    ][
        "id"
    ] == memory_id
    assert memory.get_all()[
        0
    ][
        0
    ] == memory_id


def test_replacement_signal_detection_is_explicit():
    assert has_replacement_signal(
        "Från och med nu ska vi använda fem kandidater."
    ) is True
    assert has_replacement_signal(
        "Jag gillar fem kandidater."
    ) is False


def test_conflict_detection_requires_shared_topic_not_just_category():
    active = [
        {
            "id": 1,
            "category": "preference",
            "content": "Jag föredrar modulär kod.",
        }
    ]

    conflicts = find_memory_conflicts(
        "preference",
        "Jag föredrar citron i fiskrätter.",
        active,
        threshold=0.65,
    )

    assert conflicts == []
