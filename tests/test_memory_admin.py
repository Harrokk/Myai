from copy import deepcopy

import pytest

from core.audit_log import AuditLogger
from core.config import DEFAULT_SETTINGS
from core.memory import MemoryStore
from modules.system import memory_admin


def make_store(
    tmp_path,
):
    store = MemoryStore(
        tmp_path
        / "memory.db"
    )
    store.init()
    return store


def admin_settings(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "memory"
    ][
        "database"
    ] = "memory.db"
    settings[
        "audit_logging"
    ][
        "path"
    ] = "runtime/audit.jsonl"
    return settings


def test_review_queue_deduplicates_pending_candidate(
    tmp_path,
):
    store = make_store(
        tmp_path
    )

    first = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
        reason="review",
    )
    second = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
        reason="review again",
    )

    assert first[
        "created"
    ] is True
    assert second[
        "created"
    ] is False
    assert second[
        "review_id"
    ] == first[
        "review_id"
    ]
    assert len(
        store.list_reviews()
    ) == 1


def test_review_approval_without_conflict_creates_active_memory(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
    )[
        "review_id"
    ]

    memory_id = store.approve_review(
        review_id
    )

    review = store.get_review(
        review_id
    )
    active = store.get_all()

    assert review[
        "status"
    ] == "approved"
    assert review[
        "memory_id"
    ] == memory_id
    assert len(
        active
    ) == 1
    assert active[
        0
    ][
        0
    ] == memory_id


def test_conflicting_review_cannot_be_plain_approved(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    old_id = store.save(
        "preference",
        "Jag föredrar korta tekniska svar.",
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar utförliga tekniska svar.",
        conflict_ids=[
            old_id,
        ],
    )[
        "review_id"
    ]

    with pytest.raises(
        PermissionError,
        match="måste ersätta",
    ):
        store.approve_review(
            review_id
        )

    assert store.get_review(
        review_id
    )[
        "status"
    ] == "pending"
    assert len(
        store.get_all()
    ) == 1


def test_replace_from_review_supersedes_registered_conflict_atomically(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    old_id = store.save(
        "preference",
        "Jag föredrar korta tekniska svar.",
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar utförliga tekniska svar.",
        conflict_ids=[
            old_id,
        ],
    )[
        "review_id"
    ]

    new_id = store.replace_from_review(
        review_id,
        old_id,
    )

    review = store.get_review(
        review_id
    )
    history = store.get_history()
    old = next(
        item
        for item in history
        if item[
            "id"
        ]
        == old_id
    )

    assert review[
        "status"
    ] == "replaced"
    assert review[
        "memory_id"
    ] == new_id
    assert review[
        "target_memory_id"
    ] == old_id
    assert old[
        "status"
    ] == "superseded"
    assert old[
        "superseded_by"
    ] == new_id


def test_replace_from_review_rejects_wrong_conflict_target(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    first = store.save(
        "preference",
        "Jag föredrar korta tekniska svar.",
    )
    second = store.save(
        "preference",
        "Jag föredrar modulär kod.",
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar utförliga tekniska svar.",
        conflict_ids=[
            first,
        ],
    )[
        "review_id"
    ]

    with pytest.raises(
        PermissionError,
        match="registrerade konflikter",
    ):
        store.replace_from_review(
            review_id,
            second,
        )

    assert store.get_review(
        review_id
    )[
        "status"
    ] == "pending"
    assert len(
        store.get_all()
    ) == 2


def test_reject_review_preserves_memory_database(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    memory_id = store.save(
        "project",
        "Projektet ska använda SQLite.",
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
    )[
        "review_id"
    ]

    store.reject_review(
        review_id
    )

    assert store.get_review(
        review_id
    )[
        "status"
    ] == "rejected"
    assert store.get_all()[
        0
    ][
        0
    ] == memory_id


def test_permanent_delete_removes_memory_content(
    tmp_path,
):
    store = make_store(
        tmp_path
    )
    memory_id = store.save(
        "preference",
        "Jag föredrar modulär kod.",
    )

    store.delete_memory_permanently(
        memory_id
    )

    assert store.get_all(
        include_inactive=True
    ) == []
    assert store.search(
        "modulär kod"
    ) == []


def test_memory_admin_lowercase_action_does_not_mutate(
    tmp_path,
    monkeypatch,
):
    settings = admin_settings(
        tmp_path
    )
    monkeypatch.setattr(
        memory_admin,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        memory_admin,
        "load_settings",
        lambda: settings,
    )
    store = make_store(
        tmp_path
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
    )[
        "review_id"
    ]

    result = memory_admin.memory_review_action(
        f"godkänn minnesgranskning {review_id}"
    )

    assert "Ingen minnesändring" in result
    assert store.get_review(
        review_id
    )[
        "status"
    ] == "pending"


def test_memory_admin_exact_approve_is_audited(
    tmp_path,
    monkeypatch,
):
    settings = admin_settings(
        tmp_path
    )
    monkeypatch.setattr(
        memory_admin,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        memory_admin,
        "load_settings",
        lambda: settings,
    )
    store = make_store(
        tmp_path
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
    )[
        "review_id"
    ]

    result = memory_admin.memory_review_action(
        (
            "GODKÄNN MINNESGRANSKNING "
            f"{review_id}"
        )
    )

    assert "godkändes" in result
    audit = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )
    assert "memory_review_approve" in audit
    assert '"outcome":"attempt"' in audit
    assert '"outcome":"success"' in audit
    assert "Jag föredrar modulär kod." not in audit


def test_memory_admin_audit_failure_blocks_mutation(
    tmp_path,
    monkeypatch,
):
    settings = admin_settings(
        tmp_path
    )
    monkeypatch.setattr(
        memory_admin,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        memory_admin,
        "load_settings",
        lambda: settings,
    )
    store = make_store(
        tmp_path
    )
    review_id = store.enqueue_review(
        "preference",
        "Jag föredrar modulär kod.",
    )[
        "review_id"
    ]

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

    result = memory_admin.memory_review_action(
        (
            "GODKÄNN MINNESGRANSKNING "
            f"{review_id}"
        )
    )

    assert "synthetic audit failure" in result
    assert store.get_review(
        review_id
    )[
        "status"
    ] == "pending"
    assert store.get_all() == []


def test_exact_permanent_delete_is_audited_and_removes_content(
    tmp_path,
    monkeypatch,
):
    settings = admin_settings(
        tmp_path
    )
    monkeypatch.setattr(
        memory_admin,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        memory_admin,
        "load_settings",
        lambda: settings,
    )
    store = make_store(
        tmp_path
    )
    memory_id = store.save(
        "preference",
        "Jag föredrar modulär kod.",
    )

    result = memory_admin.memory_review_action(
        f"RADERA MINNE {memory_id}"
    )

    assert "raderades permanent" in result
    assert store.get_all(
        include_inactive=True
    ) == []
    audit = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    ).read_text(
        encoding="utf-8"
    )
    assert "memory_permanent_delete" in audit
    assert "Jag föredrar modulär kod." not in audit


def test_read_only_memory_status_lists_reviews_conflicts_stale_and_history(
    tmp_path,
    monkeypatch,
):
    settings = admin_settings(
        tmp_path
    )
    settings[
        "memory"
    ][
        "stale_review_days"
    ] = 1
    monkeypatch.setattr(
        memory_admin,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        memory_admin,
        "load_settings",
        lambda: settings,
    )
    store = make_store(
        tmp_path
    )
    memory_id = store.save(
        "project",
        "Projektet ska använda SQLite.",
    )

    import sqlite3

    with sqlite3.connect(
        store.database_path
    ) as conn:
        conn.execute(
            """
            UPDATE memories
            SET created_at = '2020-01-01T00:00:00',
                updated_at = '2020-01-01T00:00:00'
            WHERE id = ?
            """,
            (
                memory_id,
            ),
        )

    review_id = store.enqueue_review(
        "project",
        "Projektet ska använda PostgreSQL.",
        conflict_ids=[
            memory_id,
        ],
    )[
        "review_id"
    ]

    reviews = memory_admin.memory_review_status(
        "Visa minnen som behöver granskas"
    )
    conflicts = memory_admin.memory_review_status(
        "Visa minneskonflikter"
    )
    stale = memory_admin.memory_review_status(
        "Visa gamla minnen"
    )
    history = memory_admin.memory_review_status(
        "Visa minneshistorik"
    )

    assert (
        f"granskning #{review_id}"
        in reviews
    )
    assert (
        f"konflikter={memory_id}"
        in conflicts
    )
    assert (
        f"minne #{memory_id}"
        in stale
    )
    assert (
        f"minne #{memory_id}"
        in history
    )


def test_memory_admin_tool_surface_has_separate_read_and_write_actions():
    assert set(
        memory_admin.TOOLS
    ) == {
        "memory_review_status",
        "memory_review_action",
    }
    assert memory_admin.TOOLS[
        "memory_review_status"
    ][
        "pass_user_input"
    ] is True
    assert memory_admin.TOOLS[
        "memory_review_action"
    ][
        "pass_user_input"
    ] is True


def test_corrupt_review_conflicts_cannot_be_plain_approved(tmp_path):
    store = make_store(tmp_path)
    review_id = store.enqueue_review(
        "preference", "Ny preferens"
    )["review_id"]
    import sqlite3

    for corrupted in ("not-json", "null", "{}", "[null]", "[true]", '["bad"]'):
        with sqlite3.connect(store.database_path) as conn:
            conn.execute(
                "UPDATE memory_reviews SET conflicts_json = ? WHERE id = ?",
                (corrupted, review_id),
            )
        with pytest.raises(ValueError, match="konfliktinformation"):
            store.approve_review(review_id)
        assert store.get_review(review_id)["status"] == "pending"
        assert store.get_all() == []


def test_corrupt_or_empty_conflicts_cannot_replace_unrelated_memory(tmp_path):
    store = make_store(tmp_path)
    target_id = store.save("preference", "Gammal preferens")
    review_id = store.enqueue_review(
        "preference", "Ny preferens"
    )["review_id"]
    import sqlite3

    for corrupted in ("not-json", "null", "[]", "{}", "[false]", '["bad"]'):
        with sqlite3.connect(store.database_path) as conn:
            conn.execute(
                "UPDATE memory_reviews SET conflicts_json = ? WHERE id = ?",
                (corrupted, review_id),
            )
        with pytest.raises((ValueError, PermissionError)):
            store.replace_from_review(review_id, target_id)
        assert store.get_review(review_id)["status"] == "pending"
        assert len(store.get_all()) == 1


def test_registered_review_conflict_still_permits_explicit_replacement(tmp_path):
    store = make_store(tmp_path)
    target_id = store.save("preference", "Gammalt")
    review_id = store.enqueue_review(
        "preference", "Nytt", conflict_ids=[target_id]
    )["review_id"]

    replacement_id = store.replace_from_review(review_id, target_id)
    assert replacement_id != target_id
    assert store.get_review(review_id)["status"] == "replaced"


def test_concurrent_review_enqueue_keeps_one_pending_record(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store = make_store(tmp_path)
    workers = 8
    gate = Barrier(workers)

    def queue(index):
        gate.wait(timeout=10)
        return store.enqueue_review(
            "PREFERENCE" if index % 2 else "preference",
            "  Samma minnesgranskning  ",
            reason="concurrent",
        )

    with ThreadPoolExecutor(max_workers=workers) as pool:
        results = list(pool.map(queue, range(workers)))

    assert sum(x["created"] for x in results) == 1
    assert len({x["review_id"] for x in results}) == 1
    assert len(store.list_reviews()) == 1


def test_existing_pending_review_escalates_to_newly_found_conflicts(tmp_path):
    store = make_store(tmp_path)
    old_id = store.save("preference", "Gammal relevant uppgift.")
    first = store.enqueue_review("preference", "Ny viktig uppgift.")
    second = store.enqueue_review(
        "PREFERENCE", " Ny viktig uppgift. ", conflict_ids=[old_id],
    )

    assert second["created"] is False
    assert second["review_id"] == first["review_id"]
    assert store.get_review(first["review_id"])["conflict_ids"] == [old_id]
    with pytest.raises(PermissionError, match="måste ersätta"):
        store.approve_review(first["review_id"])


def test_concurrent_review_conflict_union_is_preserved(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    store = make_store(tmp_path)
    old_ids = [
        store.save("preference", "Äldre inställning nummer " + str(i))
        for i in range(6)
    ]
    gate = Barrier(len(old_ids))

    def queue(old_id):
        gate.wait(timeout=10)
        return store.enqueue_review(
            "preference",
            "Ny inställning med flera kända konflikter",
            conflict_ids=[old_id],
        )

    with ThreadPoolExecutor(max_workers=len(old_ids)) as pool:
        results = list(pool.map(queue, old_ids))

    assert len({x["review_id"] for x in results}) == 1
    assert set(store.get_review(results[0]["review_id"])["conflict_ids"]) == set(old_ids)


def test_corrupt_pending_review_blocks_conflict_escalation(tmp_path):
    import sqlite3

    store = make_store(tmp_path)
    review_id = store.enqueue_review("preference", "Testvärde")["review_id"]
    with sqlite3.connect(store.database_path) as conn:
        conn.execute(
            "UPDATE memory_reviews SET conflicts_json = ? WHERE id = ?",
            ("not-json", review_id),
        )
    with pytest.raises(ValueError, match="konfliktinformation"):
        store.enqueue_review(
            "preference", "Testvärde", conflict_ids=[123]
        )
    assert len(store.list_reviews()) == 1
