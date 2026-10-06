import json
from types import SimpleNamespace

from core import ventuno_stability


class FakeClock:
    def __init__(self, values):
        self.values = iter(values)

    def __call__(self):
        return next(
            self.values
        )


class StreamingLLM:
    provider_name = "geniex"
    model = "primary-model"

    def chat_stream(
        self,
        messages,
        timeout=300,
    ):
        yield "MyAI "
        yield "OK"

    def status(self):
        return {
            "enabled": True,
            "active_backend": "primary",
            "primary_provider": "geniex",
            "primary_model": "primary-model",
            "fallback_provider": "geniex",
            "fallback_model": "fallback-model",
            "last_error": None,
        }


class FailingLLM:
    provider_name = "geniex"
    model = "primary-model"

    def chat_stream(
        self,
        messages,
        timeout=300,
    ):
        raise RuntimeError(
            "npu-fel"
        )
        yield


def test_measure_llm_iteration_records_first_chunk_and_total_time():
    clock = FakeClock(
        [
            10.0,
            10.4,
            11.2,
        ]
    )

    result = (
        ventuno_stability
        .measure_llm_iteration(
            StreamingLLM(),
            "test",
            clock=clock,
        )
    )

    assert result["success"] is True
    assert (
        result[
            "first_chunk_seconds"
        ]
        == 0.4
    )
    assert result["total_seconds"] == 1.2
    assert result["response_chars"] == 7
    assert result["response_chunks"] == 2
    assert (
        result["llm_runtime"][
            "active_backend"
        ]
        == "primary"
    )


def test_measure_llm_iteration_records_failure_without_raising():
    clock = FakeClock(
        [
            20.0,
            20.25,
        ]
    )

    result = (
        ventuno_stability
        .measure_llm_iteration(
            FailingLLM(),
            "test",
            clock=clock,
        )
    )

    assert result["success"] is False
    assert "npu-fel" in result["error"]
    assert result[
        "first_chunk_seconds"
    ] is None
    assert result["total_seconds"] == 0.25


def test_stability_logger_appends_jsonl_records(tmp_path):
    path = (
        tmp_path
        / "stability.jsonl"
    )
    logger = (
        ventuno_stability
        .VentunoStabilityLogger(
            path,
            clock=FakeClock(
                [
                    5.0,
                    7.0,
                ]
            ),
            wall_clock=lambda: 123.0,
        )
    )

    record = logger.append(
        {
            "success": True,
        },
        {
            "ram_percent": 42.0,
        },
    )

    assert record["sequence"] == 1
    assert record[
        "elapsed_seconds"
    ] == 2.0

    saved = json.loads(
        path.read_text(
            encoding="utf-8"
        ).strip()
    )
    assert saved["unix_time"] == 123.0
    assert saved["llm"][
        "success"
    ] is True
    assert saved["system"][
        "ram_percent"
    ] == 42.0


def test_collect_system_sample_is_machine_readable(monkeypatch):
    monkeypatch.setattr(
        ventuno_stability.psutil,
        "cpu_percent",
        lambda interval=None: 12.5,
    )
    monkeypatch.setattr(
        ventuno_stability.psutil,
        "virtual_memory",
        lambda: SimpleNamespace(
            percent=50.0,
            used=8,
            total=16,
        ),
    )
    monkeypatch.setattr(
        ventuno_stability.psutil,
        "disk_usage",
        lambda path: SimpleNamespace(
            percent=25.0,
            free=75,
        ),
    )
    monkeypatch.setattr(
        ventuno_stability,
        "_temperature_snapshot",
        lambda: [
            {
                "group": "soc",
                "label": "soc",
                "celsius": 55.0,
            }
        ],
    )

    sample = (
        ventuno_stability
        .collect_system_sample(
            "/"
        )
    )

    assert sample["cpu_percent"] == 12.5
    assert sample["ram_percent"] == 50.0
    assert sample["ram_used_bytes"] == 8
    assert sample["disk_free_bytes"] == 75
    assert sample["temperatures"][0][
        "celsius"
    ] == 55.0
