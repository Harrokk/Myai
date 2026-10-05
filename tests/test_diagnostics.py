import json
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from core.diagnostics import (
    build_diagnostic_report,
    format_diagnostic_report,
)
from modules.system import diagnostics


def write_json(
    path,
    value,
):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    path.write_text(
        json.dumps(
            value
        ),
        encoding="utf-8",
    )


def test_combined_diagnostics_reads_local_state_only(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    now = 1000.0

    write_json(
        tmp_path
        / "runtime"
        / "myai_health.json",
        {
            "written_unix_time": 990.0,
            "level": "healthy",
            "reasons": [
                "Inga aktiva degraderingssignaler."
            ],
            "llm_runtime": {
                "active_backend": "primary",
                "provider": "ollama",
                "model": "qwen3:8b",
            },
            "geniex_consecutive_failures": 0,
            "geniex_consecutive_successes": 0,
            "geniex_state_stale": False,
        },
    )
    write_json(
        tmp_path
        / "runtime"
        / "myai_runtime.json",
        {
            "written_unix_time": 995.0,
            "running": True,
            "llm_provider": "ollama",
            "model": "qwen3:8b",
            "component_errors": {},
            "last_error": None,
        },
    )
    (
        tmp_path
        / "runtime"
        / "errors.jsonl"
    ).write_text(
        json.dumps(
            {
                "written_unix_time": 980.0,
                "event": "tool_error",
                "component": "ram_status",
                "error_type": "RuntimeError",
                "message": "test error",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (
        tmp_path
        / "runtime"
        / "audit.jsonl"
    ).write_text(
        json.dumps(
            {
                "written_unix_time": 985.0,
                "action": "workspace_write",
                "component": "files.workspace",
                "outcome": "success",
                "target": "note.txt",
                "details": {
                    "chars": 4,
                },
            }
        )
        + "\n",
        encoding="utf-8",
    )

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=now,
    )

    assert report[
        "read_only"
    ] is True
    assert report[
        "physical_preflight_executed"
    ] is False
    assert report[
        "physical_hardware_approval"
    ] is False
    assert report[
        "configuration"
    ][
        "valid"
    ] is True
    assert report[
        "health"
    ][
        "level"
    ] == "healthy"
    assert report[
        "runtime"
    ][
        "present"
    ] is True
    assert report[
        "runtime"
    ][
        "stale"
    ] is False
    assert report[
        "recent_errors"
    ][
        "count"
    ] == 1
    assert report[
        "recent_audit"
    ][
        "count"
    ] == 1
    assert report[
        "deployment_lock"
    ][
        "observed_stack_compared"
    ] is False


def test_combined_diagnostics_marks_stale_runtime_without_mutation(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    path = (
        tmp_path
        / "runtime"
        / "myai_runtime.json"
    )
    write_json(
        path,
        {
            "written_unix_time": 100.0,
            "running": True,
        },
    )
    before = path.read_bytes()

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
    assert path.read_bytes() == before
    assert any(
        "heartbeat" in item.lower()
        for item in report[
            "concerns"
        ]
    )


def test_required_missing_deployment_lock_is_reported_without_preflight(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "deployment_lock"
    ][
        "required"
    ] = True

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=1000.0,
    )

    lock = report[
        "deployment_lock"
    ]
    assert lock[
        "required"
    ] is True
    assert lock[
        "present"
    ] is False
    assert lock[
        "blocking"
    ] is True
    assert lock[
        "observed_stack_compared"
    ] is False
    assert report[
        "physical_preflight_executed"
    ] is False


def test_structurally_valid_lock_is_not_treated_as_physical_verification(
    tmp_path,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings[
        "deployment_lock"
    ][
        "required"
    ] = True
    path = (
        tmp_path
        / "config"
        / "ventuno_stack_lock.json"
    )
    write_json(
        path,
        {
            "schema_version": 1,
            "locked": True,
            "expected": {
                "platform": {
                    "system": "Linux",
                    "machine": "aarch64",
                    "python": "3.12.0",
                },
                "geniex": {
                    "version": "example",
                },
                "packages": {
                    "arduino-router-bridge": "example",
                },
                "files": {
                    "requirements-ventuno.txt": {
                        "sha256": "example",
                    },
                },
                "models": {
                    "llm": "example",
                },
            },
        },
    )

    report = build_diagnostic_report(
        settings,
        tmp_path,
        now=1000.0,
    )

    lock = report[
        "deployment_lock"
    ]
    assert lock[
        "present"
    ] is True
    assert lock[
        "structurally_valid"
    ] is True
    assert lock[
        "observed_stack_compared"
    ] is False
    assert report[
        "physical_hardware_approval"
    ] is False


def test_formatted_diagnostics_explicitly_denies_physical_approval(
    tmp_path,
):
    report = build_diagnostic_report(
        deepcopy(
            DEFAULT_SETTINGS
        ),
        tmp_path,
        now=1000.0,
    )

    text = format_diagnostic_report(
        report
    )

    assert "MyAI samlad diagnostik" in text
    assert "Fysisk preflight körd: nej" in text
    assert (
        "Fysisk VENTUNO-verifiering: inte bedömd"
        in text
    )


def test_diagnostics_module_exposes_only_read_only_report(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        diagnostics,
        "PROJECT_ROOT",
        tmp_path,
    )

    report = (
        diagnostics
        .read_myai_diagnostic_report(
            deepcopy(
                DEFAULT_SETTINGS
            )
        )
    )

    assert report[
        "read_only"
    ] is True
    assert set(
        diagnostics.TOOLS
    ) == {
        "myai_diagnostic_report",
    }
