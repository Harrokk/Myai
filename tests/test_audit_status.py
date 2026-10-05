import json
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from modules.system import audit


def test_audit_status_reports_no_events(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    monkeypatch.setattr(
        audit,
        "PROJECT_ROOT",
        tmp_path,
    )

    result = audit.read_myai_audit_status(
        settings
    )

    assert result["enabled"] is True
    assert result["records"] == []
    assert (
        audit.format_myai_audit_status(
            result
        )
        == "Inga audit-händelser finns i den aktuella loggen."
    )


def test_audit_status_reads_latest_event_read_only(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    monkeypatch.setattr(
        audit,
        "PROJECT_ROOT",
        tmp_path,
    )
    path = (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    )
    path.parent.mkdir(
        parents=True,
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "written_unix_time": 1.0,
                "action": "workspace_write",
                "component": "files.workspace",
                "outcome": "success",
                "target": "notes.txt",
                "details": {
                    "chars": 4,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )
    before = path.read_bytes()

    result = audit.read_myai_audit_status(
        settings
    )
    text = audit.format_myai_audit_status(
        result
    )

    assert result["count"] == 1
    assert "workspace_write" in text
    assert "success" in text
    assert "notes.txt" in text
    assert path.read_bytes() == before


def test_audit_status_respects_disabled_logging(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["audit_logging"][
        "enabled"
    ] = False
    settings["audit_logging"][
        "require_for_writes"
    ] = False
    monkeypatch.setattr(
        audit,
        "PROJECT_ROOT",
        tmp_path,
    )

    result = audit.read_myai_audit_status(
        settings
    )

    assert result["enabled"] is False
    assert (
        audit.format_myai_audit_status(
            result
        )
        == "MyAI:s audit-loggning är avstängd."
    )


def test_audit_tool_exposes_only_read_only_status():
    assert set(
        audit.TOOLS
    ) == {
        "myai_audit_status",
    }
