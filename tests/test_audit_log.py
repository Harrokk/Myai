import json

import pytest

from core import audit_log
from core.audit_log import (
    AuditLogger,
    audit_outcome_for_exception,
    read_recent_audit,
)


def settings(
    *,
    enabled=True,
    required=True,
):
    return {
        "audit_logging": {
            "enabled": enabled,
            "require_for_writes": required,
            "path": "runtime/audit.jsonl",
            "max_detail_chars": 64,
            "recent_limit": 20,
        },
        "logging": {
            "jsonl_max_bytes": 1000,
            "jsonl_backups": 2,
        },
    }


def read_rows(path):
    return [
        json.loads(
            line
        )
        for line in path.read_text(
            encoding="utf-8"
        ).splitlines()
        if line.strip()
    ]


def test_audit_logger_writes_structured_record_without_payload(tmp_path):
    logger = AuditLogger(
        settings(),
        tmp_path,
        wall_clock=lambda: 123.5,
    )

    assert logger.write_attempt(
        action="workspace_write",
        component="files.workspace",
        target="notes.txt",
        details={
            "chars": 12,
        },
    ) is True

    row = read_rows(
        tmp_path
        / "runtime"
        / "audit.jsonl"
    )[0]

    assert row["written_unix_time"] == 123.5
    assert row["action"] == "workspace_write"
    assert row["outcome"] == "attempt"
    assert row["target"] == "notes.txt"
    assert row["details"] == {
        "chars": 12,
    }
    assert "prompt" not in row
    assert "content" not in row
    assert "approval_phrase" not in row


def test_required_audit_blocks_when_disabled(tmp_path):
    logger = AuditLogger(
        settings(
            enabled=False,
            required=True,
        ),
        tmp_path,
    )

    with pytest.raises(
        RuntimeError,
        match="krävs",
    ):
        logger.write_attempt(
            action="workspace_write",
            component="files.workspace",
            target="notes.txt",
        )


def test_required_audit_blocks_when_storage_fails(
    tmp_path,
    monkeypatch,
):
    logger = AuditLogger(
        settings(),
        tmp_path,
    )

    def fail(*args, **kwargs):
        raise OSError(
            "disk unavailable"
        )

    monkeypatch.setattr(
        audit_log,
        "append_jsonl",
        fail,
    )

    with pytest.raises(
        RuntimeError,
        match="blockeras",
    ):
        logger.write_attempt(
            action="workspace_write",
            component="files.workspace",
            target="notes.txt",
        )


def test_result_logging_is_best_effort(tmp_path, monkeypatch):
    logger = AuditLogger(
        settings(),
        tmp_path,
    )

    def fail(*args, **kwargs):
        raise OSError(
            "disk unavailable"
        )

    monkeypatch.setattr(
        audit_log,
        "append_jsonl",
        fail,
    )

    assert logger.write_result(
        action="workspace_write",
        component="files.workspace",
        outcome="success",
        target="notes.txt",
    ) is False


def test_audit_outcome_classifies_denials():
    assert audit_outcome_for_exception(
        PermissionError(
            "nej"
        )
    ) == "denied"
    assert audit_outcome_for_exception(
        RuntimeError(
            "Skrivning är avstängd."
        )
    ) == "denied"
    assert audit_outcome_for_exception(
        OSError(
            "diskfel"
        )
    ) == "failed"


def test_read_recent_audit_reads_rotated_and_ignores_malformed(
    tmp_path,
):
    path = (
        tmp_path
        / "audit.jsonl"
    )
    (
        tmp_path
        / "audit.jsonl.1"
    ).write_text(
        '{"written_unix_time":1,"action":"old","component":"test","outcome":"success","target":null,"details":{}}\n',
        encoding="utf-8",
    )
    path.write_text(
        'broken\n'
        '{"written_unix_time":2,"action":"new","component":"test","outcome":"denied","target":"x","details":{}}\n',
        encoding="utf-8",
    )

    result = read_recent_audit(
        path,
        limit=2,
        backups=2,
    )

    assert [
        item["action"]
        for item in result[
            "records"
        ]
    ] == [
        "new",
        "old",
    ]
    assert result[
        "malformed_count"
    ] == 1
