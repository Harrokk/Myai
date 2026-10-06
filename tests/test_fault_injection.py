import json
from copy import deepcopy
from pathlib import Path

import pytest

from core import health_status
from core.audit_log import AuditLogger
from core.config import DEFAULT_SETTINGS
from core.diagnostics import build_diagnostic_report
from core.geniex_supervisor import GenieXSupervisor
from core.resilient_llm import ResilientLLMClient
from modules.files import workspace


class FaultLLM:
    def __init__(
        self,
        *,
        name="geniex",
        model="test",
        chat_value="ok",
        chat_error=None,
        stream_values=None,
        stream_error_before=None,
        stream_error_after=None,
    ):
        self.provider_name = name
        self.model = model
        self.url = "http://local.test"
        self.chat_value = chat_value
        self.chat_error = chat_error
        self.stream_values = list(
            stream_values
            or []
        )
        self.stream_error_before = (
            stream_error_before
        )
        self.stream_error_after = (
            stream_error_after
        )
        self.chat_calls = 0
        self.stream_calls = 0

    def chat(
        self,
        messages,
        timeout=300,
    ):
        self.chat_calls += 1

        if self.chat_error is not None:
            raise self.chat_error

        return self.chat_value

    def chat_stream(
        self,
        messages,
        timeout=300,
    ):
        self.stream_calls += 1

        if self.stream_error_before is not None:
            raise self.stream_error_before

        for value in self.stream_values:
            yield value

        if self.stream_error_after is not None:
            raise self.stream_error_after


def writable_workspace_settings(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "files"
    ][
        "workspace_root"
    ] = str(
        tmp_path
        / "workspace"
    )
    settings[
        "files"
    ][
        "write_enabled"
    ] = True
    settings[
        "audit_logging"
    ][
        "path"
    ] = str(
        tmp_path
        / "runtime"
        / "audit.jsonl"
    )
    return settings


def test_fault_primary_timeout_falls_back_for_nonstreaming():
    primary = FaultLLM(
        chat_error=TimeoutError(
            "synthetic provider timeout"
        )
    )
    fallback = FaultLLM(
        model="fallback",
        chat_value="fallback answer",
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    assert client.chat(
        []
    ) == "fallback answer"
    assert primary.chat_calls == 1
    assert fallback.chat_calls == 1
    status = client.status()
    assert status[
        "active_backend"
    ] == "fallback"
    assert (
        "synthetic provider timeout"
        in status[
            "last_error"
        ]
    )


def test_fault_stream_timeout_before_first_token_falls_back():
    primary = FaultLLM(
        stream_error_before=TimeoutError(
            "synthetic first-token timeout"
        )
    )
    fallback = FaultLLM(
        model="fallback",
        stream_values=[
            "safe ",
            "fallback",
        ],
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )

    assert list(
        client.chat_stream(
            []
        )
    ) == [
        "safe ",
        "fallback",
    ]
    assert primary.stream_calls == 1
    assert fallback.stream_calls == 1
    assert client.status()[
        "active_backend"
    ] == "fallback"


def test_fault_stream_failure_after_first_token_never_mixes_fallback():
    primary = FaultLLM(
        stream_values=[
            "partial",
        ],
        stream_error_after=ConnectionError(
            "synthetic disconnect after token"
        ),
    )
    fallback = FaultLLM(
        model="fallback",
        stream_values=[
            "must-not-appear",
        ],
    )
    client = ResilientLLMClient(
        primary,
        fallback,
        enabled=True,
    )
    stream = client.chat_stream(
        []
    )

    assert next(
        stream
    ) == "partial"

    with pytest.raises(
        ConnectionError,
        match="after token",
    ):
        next(
            stream
        )

    assert fallback.stream_calls == 0


def test_fault_corrupt_health_and_runtime_snapshots_are_safe_and_read_only(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    health_path = (
        tmp_path
        / "runtime"
        / "myai_health.json"
    )
    runtime_path = (
        tmp_path
        / "runtime"
        / "myai_runtime.json"
    )
    health_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    health_path.write_text(
        "{broken-health",
        encoding="utf-8",
    )
    runtime_path.write_text(
        "{broken-runtime",
        encoding="utf-8",
    )
    before_health = (
        health_path.read_bytes()
    )
    before_runtime = (
        runtime_path.read_bytes()
    )

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=1000.0,
    )

    assert report[
        "health"
    ][
        "snapshot_stale"
    ] is True
    assert report[
        "runtime"
    ][
        "present"
    ] is False
    assert report[
        "physical_preflight_executed"
    ] is False
    assert health_path.read_bytes() == before_health
    assert runtime_path.read_bytes() == before_runtime


def test_fault_corrupt_error_and_audit_logs_are_ignored_not_executed(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    runtime = (
        tmp_path
        / "runtime"
    )
    runtime.mkdir(
        parents=True,
        exist_ok=True,
    )
    (
        runtime
        / "errors.jsonl"
    ).write_text(
        "not-json\n"
        + json.dumps(
            {
                "written_unix_time": 1,
                "event": "tool_error",
                "component": "cpu_status",
                "error_type": "RuntimeError",
                "message": "synthetic",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (
        runtime
        / "audit.jsonl"
    ).write_text(
        "also-not-json\n"
        + json.dumps(
            {
                "written_unix_time": 2,
                "action": "workspace_write",
                "component": "files.workspace",
                "outcome": "denied",
                "target": "x.txt",
                "details": {},
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=1000.0,
    )

    assert report[
        "recent_errors"
    ][
        "count"
    ] == 1
    assert report[
        "recent_errors"
    ][
        "malformed_count"
    ] == 1
    assert report[
        "recent_audit"
    ][
        "count"
    ] == 1
    assert report[
        "recent_audit"
    ][
        "malformed_count"
    ] == 1


def test_fault_stale_runtime_and_watchdog_do_not_look_healthy(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "llm"
    ][
        "provider"
    ] = "geniex"
    settings[
        "geniex_supervisor"
    ][
        "enabled"
    ] = True

    runtime = (
        tmp_path
        / "runtime"
    )
    runtime.mkdir(
        parents=True,
        exist_ok=True,
    )
    (
        runtime
        / "myai_runtime.json"
    ).write_text(
        json.dumps(
            {
                "written_unix_time": 100.0,
                "running": True,
            }
        ),
        encoding="utf-8",
    )
    (
        runtime
        / "geniex_health.json"
    ).write_text(
        json.dumps(
            {
                "written_unix_time": 100.0,
                "check": {
                    "enabled": True,
                    "healthy": True,
                    "consecutive_failures": 0,
                    "consecutive_successes": 5,
                },
            }
        ),
        encoding="utf-8",
    )

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=1000.0,
    )

    assert report[
        "runtime"
    ][
        "stale"
    ] is True
    assert report[
        "health"
    ][
        "level"
    ] == "unknown"
    assert report[
        "health"
    ][
        "geniex_state_stale"
    ] is True


def test_fault_required_audit_storage_failure_blocks_workspace_before_write(
    tmp_path,
    monkeypatch,
):
    settings = (
        writable_workspace_settings(
            tmp_path
        )
    )
    monkeypatch.setattr(
        workspace,
        "PROJECT_ROOT",
        tmp_path,
    )
    monkeypatch.setattr(
        workspace,
        "load_settings",
        lambda: settings,
    )

    def block_attempt(
        self,
        **kwargs,
    ):
        raise RuntimeError(
            "synthetic audit storage failure"
        )

    monkeypatch.setattr(
        AuditLogger,
        "write_attempt",
        block_attempt,
    )

    result = workspace.workspace_write(
        'Skapa filen "blocked.txt" med innehållet hemligt.'
    )

    assert "synthetic audit storage failure" in result
    assert not (
        tmp_path
        / "workspace"
        / "blocked.txt"
    ).exists()


def test_fault_unwritable_workspace_storage_leaves_no_target(
    tmp_path,
    monkeypatch,
):
    settings = (
        writable_workspace_settings(
            tmp_path
        )
    )
    original_write_text = (
        Path.write_text
    )

    def fail_temp_write(
        self,
        data,
        *args,
        **kwargs,
    ):
        if str(
            self
        ).endswith(
            ".tmp"
        ):
            raise OSError(
                "synthetic disk full"
            )

        return original_write_text(
            self,
            data,
            *args,
            **kwargs,
        )

    monkeypatch.setattr(
        Path,
        "write_text",
        fail_temp_write,
    )

    with pytest.raises(
        OSError,
        match="disk full",
    ):
        workspace.write_workspace_text(
            "full.txt",
            "payload",
            settings=settings,
        )

    assert not (
        tmp_path
        / "workspace"
        / "full.txt"
    ).exists()
    assert not (
        tmp_path
        / "workspace"
        / "full.txt.tmp"
    ).exists()


def test_fault_atomic_health_replace_failure_preserves_previous_snapshot(
    tmp_path,
    monkeypatch,
):
    path = (
        tmp_path
        / "health.json"
    )
    path.write_text(
        json.dumps(
            {
                "level": "healthy",
                "written_unix_time": 1.0,
            }
        ),
        encoding="utf-8",
    )
    before = path.read_bytes()

    def fail_replace(
        source,
        target,
    ):
        raise OSError(
            "synthetic replace failure"
        )

    monkeypatch.setattr(
        health_status.os,
        "replace",
        fail_replace,
    )

    with pytest.raises(
        OSError,
        match="replace failure",
    ):
        health_status.write_health_state(
            path,
            {
                "level": "degraded",
            },
        )

    assert path.read_bytes() == before
    assert list(
        tmp_path.glob(
            "health.json.*.tmp"
        )
    ) == []


def test_fault_geniex_timeouts_never_restart_when_restart_gate_is_off():
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "geniex_supervisor"
    ].update(
        {
            "enabled": True,
            "failure_threshold": 2,
            "restart_enabled": False,
            "restart_command": [],
        }
    )
    restart_calls = []

    def timeout_get(
        url,
        timeout,
    ):
        raise TimeoutError(
            "synthetic watchdog timeout"
        )

    supervisor = GenieXSupervisor(
        settings,
        request_get=timeout_get,
        command_runner=(
            lambda command, timeout: (
                restart_calls.append(
                    (
                        command,
                        timeout,
                    )
                )
            )
        ),
    )

    first = supervisor.supervise_once()
    second = supervisor.supervise_once()

    assert first[
        "check"
    ][
        "healthy"
    ] is False
    assert second[
        "check"
    ][
        "consecutive_failures"
    ] == 2
    assert second[
        "restart"
    ][
        "attempted"
    ] is False
    assert restart_calls == []
