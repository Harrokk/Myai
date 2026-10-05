import json
from copy import deepcopy

from core.config import DEFAULT_SETTINGS
from modules.system import health


def test_read_myai_health_uses_fresh_saved_snapshot(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["health"] = {
        "state_path": "runtime/myai_health.json",
        "state_stale_seconds": 60,
    }
    monkeypatch.setattr(
        health,
        "PROJECT_ROOT",
        tmp_path,
    )
    path = (
        tmp_path
        / "runtime"
        / "myai_health.json"
    )
    path.parent.mkdir(
        parents=True,
    )
    path.write_text(
        json.dumps(
            {
                "level": "degraded",
                "reasons": [
                    "LLM kör reservbackend."
                ],
                "llm_runtime": {
                    "active_backend": "fallback",
                    "provider": "geniex",
                    "model": "primary-model",
                },
                "geniex_healthy": False,
                "geniex_consecutive_failures": 3,
                "written_unix_time": 100.0,
            }
        ),
        encoding="utf-8",
    )

    result = health.read_myai_health(
        settings,
        now=110,
    )

    assert result["level"] == "degraded"
    assert result["snapshot_stale"] is False
    assert result["snapshot_age_seconds"] == 10.0


def test_read_myai_health_reconstructs_when_snapshot_is_stale(
    tmp_path,
    monkeypatch,
):
    settings = deepcopy(
        DEFAULT_SETTINGS
    )
    settings["llm"]["provider"] = "geniex"
    settings["geniex_supervisor"]["enabled"] = True
    settings["health"] = {
        "state_path": "runtime/myai_health.json",
        "state_stale_seconds": 10,
    }
    settings["geniex_supervisor"]["state_path"] = (
        "runtime/geniex_health.json"
    )
    settings["geniex_supervisor"]["state_stale_seconds"] = 30

    monkeypatch.setattr(
        health,
        "PROJECT_ROOT",
        tmp_path,
    )

    runtime_dir = (
        tmp_path
        / "runtime"
    )
    runtime_dir.mkdir()

    (
        runtime_dir
        / "myai_health.json"
    ).write_text(
        json.dumps(
            {
                "level": "healthy",
                "written_unix_time": 1.0,
            }
        ),
        encoding="utf-8",
    )
    (
        runtime_dir
        / "geniex_health.json"
    ).write_text(
        json.dumps(
            {
                "written_unix_time": 95.0,
                "check": {
                    "enabled": True,
                    "healthy": False,
                    "consecutive_failures": 2,
                },
                "restart": {
                    "attempted": False,
                },
            }
        ),
        encoding="utf-8",
    )

    result = health.read_myai_health(
        settings,
        now=100,
    )

    assert result["level"] == "unhealthy"
    assert result["snapshot_stale"] is True
    assert result["geniex_consecutive_failures"] == 2


def test_health_format_reports_backend_and_failures():
    text = health.format_myai_health(
        {
            "level": "degraded",
            "llm_runtime": {
                "active_backend": "fallback",
                "provider": "geniex",
                "model": "primary-model",
            },
            "geniex_healthy": False,
            "geniex_consecutive_failures": 3,
            "reasons": [
                "LLM kör reservbackend.",
            ],
            "snapshot_stale": False,
            "snapshot_age_seconds": 2.0,
        }
    )

    assert "MyAI-hälsa: degraderad" in text
    assert "Aktiv backend: fallback" in text
    assert "GenieX-fel i rad: 3" in text
    assert "Snapshot-ålder: 2.0 s" in text


def test_health_tool_exposes_only_read_only_status():
    assert set(
        health.TOOLS
    ) == {
        "myai_health_status",
    }



def test_health_format_marks_stale_geniex_as_unknown():
    text = health.format_myai_health(
        {
            "level": "unknown",
            "llm_runtime": {
                "active_backend": "primary",
                "provider": "geniex",
                "model": "primary-model",
            },
            "geniex_healthy": False,
            "geniex_state_stale": True,
            "geniex_consecutive_failures": 2,
            "reasons": [
                "GenieX watchdog-status saknas eller är för gammal.",
            ],
            "snapshot_stale": True,
        }
    )

    assert "GenieX readiness: stale/unknown" in text
    assert "GenieX readiness: unhealthy" not in text
