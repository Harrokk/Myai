import json

from core import error_log
from core.error_log import ErrorLogger


def settings(
    *,
    enabled=True,
):
    return {
        "error_logging": {
            "enabled": enabled,
            "path": "runtime/errors.jsonl",
            "max_message_chars": 80,
        },
        "logging": {
            "jsonl_max_bytes": 1000,
            "jsonl_backups": 2,
        },
    }


def test_error_logger_writes_structured_record_without_user_prompt(
    tmp_path,
):
    logger = ErrorLogger(
        settings(),
        tmp_path,
        wall_clock=lambda: 123.5,
    )

    assert logger.log_exception(
        "tool_error",
        "ram_status",
        RuntimeError(
            "first line\nsecond line"
        ),
    ) is True

    path = (
        tmp_path
        / "runtime"
        / "errors.jsonl"
    )
    record = json.loads(
        path.read_text(
            encoding="utf-8"
        ).strip()
    )

    assert record == {
        "schema_version": 1,
        "written_unix_time": 123.5,
        "event": "tool_error",
        "component": "ram_status",
        "error_type": "RuntimeError",
        "message": "Details withheld",
    }
    assert "user_input" not in record
    assert "prompt" not in record


def test_error_logger_truncates_long_messages(
    tmp_path,
):
    logger = ErrorLogger(
        settings(),
        tmp_path,
    )

    logger.log_exception(
        "tool_error",
        "test_tool",
        ValueError(
            "x" * 200
        ),
    )

    record = json.loads(
        (
            tmp_path
            / "runtime"
            / "errors.jsonl"
        ).read_text(
            encoding="utf-8"
        ).strip()
    )

    assert record["message"] == "Details withheld"
    assert "x" * 20 not in record["message"]


def test_disabled_error_logger_does_not_write(
    tmp_path,
):
    logger = ErrorLogger(
        settings(
            enabled=False
        ),
        tmp_path,
    )

    assert logger.log_exception(
        "tool_error",
        "cpu_status",
        RuntimeError(
            "test"
        ),
    ) is False

    assert not (
        tmp_path
        / "runtime"
        / "errors.jsonl"
    ).exists()


def test_error_log_failure_never_raises(
    tmp_path,
    monkeypatch,
):
    logger = ErrorLogger(
        settings(),
        tmp_path,
    )

    def fail(*args, **kwargs):
        raise OSError(
            "disk unavailable"
        )

    monkeypatch.setattr(
        error_log,
        "append_jsonl",
        fail,
    )

    assert logger.log_exception(
        "tool_error",
        "disk_status",
        RuntimeError(
            "original failure"
        ),
    ) is False


def test_read_recent_errors_reads_current_before_rotated(tmp_path):
    from core.error_log import read_recent_errors

    path = tmp_path / "errors.jsonl"
    path.write_text(
        '{"written_unix_time":3,"event":"tool_error","component":"new","error_type":"RuntimeError","message":"newest"}\n',
        encoding="utf-8",
    )
    (
        tmp_path
        / "errors.jsonl.1"
    ).write_text(
        '{"written_unix_time":2,"event":"tool_error","component":"old","error_type":"ValueError","message":"older"}\n',
        encoding="utf-8",
    )

    result = read_recent_errors(
        path,
        limit=2,
        backups=2,
    )

    assert [
        item["component"]
        for item in result["records"]
    ] == [
        "new",
        "old",
    ]


def test_read_recent_errors_ignores_malformed_lines(tmp_path):
    from core.error_log import read_recent_errors

    path = tmp_path / "errors.jsonl"
    path.write_text(
        'not-json\n'
        '{"written_unix_time":4,"event":"tool_error","component":"cpu_status","error_type":"RuntimeError","message":"failed"}\n',
        encoding="utf-8",
    )

    result = read_recent_errors(
        path,
        limit=10,
        backups=0,
    )

    assert result["count"] == 1
    assert result["malformed_count"] == 1
    assert result["records"][0][
        "component"
    ] == "cpu_status"


def test_read_recent_errors_caps_limit_at_50(tmp_path):
    from core.error_log import read_recent_errors

    path = tmp_path / "errors.jsonl"
    rows = [
        (
            '{"written_unix_time":'
            + str(index)
            + ',"event":"tool_error","component":"tool_'
            + str(index)
            + '","error_type":"RuntimeError","message":"x"}'
        )
        for index in range(60)
    ]
    path.write_text(
        "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )

    result = read_recent_errors(
        path,
        limit=1000,
        backups=0,
    )

    assert result["count"] == 50
    assert result["records"][0][
        "component"
    ] == "tool_59"
    assert result["records"][-1][
        "component"
    ] == "tool_10"



def test_logged_exception_does_not_persist_credentials_or_user_audio(tmp_path):
    marker = "PRIVATE-NOT-FOR-LOGS-bearer-user-speech"
    logger = ErrorLogger(settings(), tmp_path, wall_clock=lambda: 170.0)
    assert logger.log_exception("tool_error", "device", RuntimeError(marker))
    content = (tmp_path / "runtime/errors.jsonl").read_text(encoding="utf-8")
    assert marker not in content
    assert "Details withheld" in content
    assert '"error_type": "RuntimeError"' in content


def test_old_log_exception_text_is_not_exposed_on_read(tmp_path):
    from core.error_log import read_recent_errors
    marker = "OLD-EXCEPTION-CONTAINING-USER-PROMPT"
    path = tmp_path / "errors.jsonl"
    path.write_text(
        json.dumps({"written_unix_time": 8,
                    "event": "tool_error", "component": "camera",
                    "error_type": "OSError", "message": marker}) + "\n",
        encoding="utf-8",
    )
    report = read_recent_errors(path, limit=10, backups=0)
    assert report["count"] == 1
    assert marker not in str(report)
    assert report["records"][0]["message"] == "Details withheld"
