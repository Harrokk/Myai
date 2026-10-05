import json
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from modules.system import errors


def test_recent_error_tool_reports_no_errors(tmp_path, monkeypatch):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    monkeypatch.setattr(
        errors,
        "PROJECT_ROOT",
        tmp_path,
    )

    result = errors.read_myai_recent_errors(
        settings
    )

    assert result["enabled"] is True
    assert result["records"] == []
    assert (
        errors.format_myai_recent_errors(
            result
        )
        == "Inga strukturerade MyAI-fel finns i den aktuella felloggen."
    )


def test_recent_error_tool_reads_and_formats_latest_error(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    monkeypatch.setattr(
        errors,
        "PROJECT_ROOT",
        tmp_path,
    )
    path = (
        tmp_path
        / "runtime"
        / "errors.jsonl"
    )
    path.parent.mkdir(
        parents=True,
    )
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "written_unix_time": 1.0,
                "event": "tool_error",
                "component": "ram_status",
                "error_type": "RuntimeError",
                "message": "sensor unavailable",
            }
        )
        + "\n",
        encoding="utf-8",
    )

    result = errors.read_myai_recent_errors(
        settings
    )
    text = errors.format_myai_recent_errors(
        result
    )

    assert result["count"] == 1
    assert "ram_status" in text
    assert "RuntimeError" in text
    assert "sensor unavailable" in text


def test_recent_error_tool_respects_disabled_logging(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["error_logging"][
        "enabled"
    ] = False
    monkeypatch.setattr(
        errors,
        "PROJECT_ROOT",
        tmp_path,
    )

    result = errors.read_myai_recent_errors(
        settings
    )

    assert result["enabled"] is False
    assert (
        errors.format_myai_recent_errors(
            result
        )
        == "MyAI:s lokala felloggning är avstängd."
    )


def test_recent_error_tool_exposes_only_read_only_action():
    assert set(
        errors.TOOLS
    ) == {
        "myai_recent_errors",
    }
